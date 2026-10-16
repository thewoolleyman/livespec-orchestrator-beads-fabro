"""Herdr pane targets observed by the bounded host-session wait.

Scenario 155 of `SPECIFICATION/scenarios.md` governs this module: only a
`working` pane continues a wait, and every other state ends it with the actual
observed state or a distinct diagnostic outcome.

TWO CLASSES OF PEER ARE USED HERE, and the difference is disclosed rather than
blurred, because they prove different things.

A REAL ISOLATED HERDR SERVER is the behavioural proof, and those tests live in
`tests/e2e/test_session_wait_pane_live_herdr.py`: they need the `herdr` binary,
which CI does not carry, and a skipped body is not a line any CI leg ran. Every
branch of the adapter is reachable from THIS module without it, which is what
keeps the per-file coverage gate honest on a host with no herdr.

CONTROLLED PEERS (`_controlled_peer`) are local unix sockets answering with
bytes a test dictates. They exist for the protocol failures a healthy server
cannot be asked to produce — a truncated reply, a reply that is not an object,
a reply with no agent record. They are never used for a state transition a
real server can perform.

Nothing here touches a pane, workspace or server this test did not create.
"""

from __future__ import annotations

import importlib
import itertools
import json
import shutil
import socket
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"

# Every state a Herdr pane can report. A diagnostic must never be rendered as
# one of these: an unreadable reply presented as `unknown` would turn "this
# probe failed" into "the server reports the agent's state as uncertain",
# which is a claim about the agent that nobody measured.
_PANE_STATES = frozenset({"working", "idle", "done", "blocked", "unknown"})

# `sizeof(sun_path)` is 108 bytes including the terminator on Linux.
_SUN_PATH_LIMIT = 107

# The observation instant handed to every poll below. A fixed value, because
# nothing here grades WHEN an observation was taken: a probe records the instant
# it was given, so reading the host clock for it would only make the recorded
# value unpredictable without making any assertion stronger.
_FIXED_OBSERVED_AT = 1.0
# A failure bound on joining a worker that has already been asked to finish,
# never a timing assertion: the join's own return is what the wait is for, and
# the `is_alive` check after it is what reports a worker that did not.
_WORKER_JOIN_SECONDS = 30.0
# The read budget granted to the probe whose peer never answers. Small, because
# the case waits out that budget on purpose and the adapter adds a fixed grace
# of its own on top; what matters is only that the read cannot complete early.
_HANGING_BUDGET_SECONDS = 0.05


def _module(*, name: str) -> object:
    """One session-wait module, imported inside the test body.

    The import is deliberately NOT at module top: the Red moment of this
    slice runs the pane behaviour against minimal failing stubs of the new
    adapter modules, and a top-level import would turn a later absence into a
    collection error — which proves only unimportability, not that the
    behaviour is unimplemented.
    """
    return importlib.import_module(f"{_COMMANDS}.{name}")


@contextmanager
def _hanging_peer(*, name: str):
    """A BOUND socket with no accept loop, so a probe's read genuinely hangs.

    This exists to make an in-flight observation a FACT rather than a race. A
    unix `connect` completes against the kernel's listen backlog without
    anybody accepting it, and the request then sits in the socket buffer
    unanswered, so the probe's read blocks for its whole budget — which is what
    lets a case assert that the first poll has no answer yet and then wait on
    the worker's own exit.

    It owns a SHORT root for the same `sun_path` reason `_controlled_peer`
    does, and asserts the bound for the same reason: a future rename that
    lengthens the name fails loudly and once instead of flaking per worker.
    """
    with _short_root() as directory:
        socket_path = directory / name
        assert len(str(socket_path)) <= _SUN_PATH_LIMIT, (
            f"{socket_path} is {len(str(socket_path))} bytes, over the"
            f" {_SUN_PATH_LIMIT}-byte sun_path limit"
        )
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(8)
        try:
            yield socket_path
        finally:
            listener.close()


@contextmanager
def _short_root():
    """A SHORT owned directory for a herdr server's XDG roots.

    NOT `tmp_path`, and that is a measured constraint rather than a deviation
    for its own sake. A unix socket path is capped by `sizeof(sun_path)` — 108
    bytes including the terminator, so 107 usable — and herdr binds TWO
    sockets in its config directory, of which `herdr-client.sock` has the
    longer name. Measured on this host: under `tmp_path` a serial run produces
    a 98-byte client path and fits, while any `pytest -n` run inserts a
    `popen-gwNN` segment and produces 109 bytes, one over. The server then
    exits 1 with `local socket name length exceeds capacity of sun_path of
    sockaddr_un`, which surfaces as an unready-server flake naming no path
    length anywhere but the server's own log. Since `just check` runs the
    suite in parallel, a `tmp_path` root cannot pass it at all.

    It is a separate context from the server so that a RESTART can reuse the
    same root, and therefore the same socket path — which is the only way to
    exercise a changed server generation at a path that did not move.
    """
    directory = Path(tempfile.mkdtemp(prefix="livespec-herdr-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _answer_once(*, connection: socket.socket, reply: bytes) -> None:
    with suppress(OSError):
        _ = connection.recv(65536)
        if reply:
            connection.sendall(reply)
        connection.close()


@contextmanager
def _controlled_peer(*, name: str, replies: list[bytes]):
    """A unix socket answering each connection with scripted bytes.

    The listener is bound synchronously BEFORE the context is entered, so a
    test never races its own peer: there is no readiness window to poll and
    no deadline to expire. Only the accept loop is threaded, and it is joined
    on the way out.

    It OWNS its own short root and YIELDS the path it bound, rather than
    binding a path a caller chose. The `sun_path` bound belongs to whatever
    binds the socket, and a caller passing `tmp_path` cannot honour it: under
    `pytest -n` that prefix gains a `popen-gwNN` segment, and a peer named for
    one of this module's longer reply labels then overflows 107 bytes and dies
    with `AF_UNIX path too long`. That is invisible to a serial run and fails
    `just check`, which runs the suite in parallel — measured on
    `observe-over-the-reply-ceiling.sock`. `_short_root` carries the same
    bound for the server's own sockets, and the assertion below is here for
    the same reason it is there: a future rename that lengthens a name fails
    loudly and once instead of flaking per worker.
    """
    with _short_root() as directory:
        socket_path = directory / name
        assert len(str(socket_path)) <= _SUN_PATH_LIMIT, (
            f"{socket_path} is {len(str(socket_path))} bytes, over the"
            f" {_SUN_PATH_LIMIT}-byte sun_path limit"
        )
        stop = threading.Event()
        served = itertools.count()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(8)
        listener.settimeout(0.05)

        def serve() -> None:
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except OSError:
                    continue
                reply = replies[min(next(served), len(replies) - 1)]
                threading.Thread(
                    target=_answer_once,
                    kwargs={"connection": connection, "reply": reply},
                    daemon=True,
                ).start()

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield socket_path
        finally:
            stop.set()
            worker.join(timeout=30.0)
            listener.close()


def _agent_reply(*, agent: dict[str, object]) -> bytes:
    envelope = {"id": "test", "result": {"type": "agent_info", "agent": agent}}
    return json.dumps(envelope).encode("utf-8") + b"\n"


def _cli_seams(*, repository: Path):
    del repository
    session_wait = _module(name="session_wait")
    routing = _module(name="_session_wait_routing")
    records = _module(name="_session_wait_records")
    return session_wait.SessionWaitCliSeams(
        primary_repository=lambda *, repository: repository,
        launcher=routing.default_wait_launcher,
        observe_target=routing.observe_wait_target,
        process_generation=records.process_generation_token,
        wall_clock=time.time,
    )


def _observed_through_its_own_worker(*, probe: object):
    """One observation from a probe, waited for by JOINING its own worker.

    The pane adapter runs each observation on a thread of its own and answers
    `None` while that work is in flight, so the deterministic event this waits
    on is the WORKER EXITING: the first poll starts it, the join is the signal
    that it finished, and the second poll reads the landed result. A poll loop
    sampling the host clock answers the same question by guessing how long the
    thread needs, which is the shape that fails under load.

    The caller OWES a target whose observation cannot complete promptly, which
    is why `_hanging_peer` exists. Against a socket path that does not exist
    the worker can finish between `Thread.start()` returning and the first poll
    reading its result, so the first `None` would be a race rather than a fact
    — and a case that branches on which way that race fell is waiting on
    scheduling with extra steps.
    """
    assert probe.poll(now=_FIXED_OBSERVED_AT) is None, "the observation was not in flight"
    task = probe.task
    assert task is not None, "the probe started no observation"
    assert task.thread is not None, "the observation started no worker"
    task.thread.join(timeout=_WORKER_JOIN_SECONDS)
    assert task.thread.is_alive() is False, "the pane worker never finished"
    observation = probe.poll(now=_FIXED_OBSERVED_AT)
    assert observation is not None, "the probe never produced an observation"
    return observation


def test_a_pane_identity_cannot_be_forged_through_its_own_separators(
    *,
    tmp_path: Path,
) -> None:
    """A colon or a space inside one component cannot forge another."""
    types_module = _module(name="_session_wait_types")
    awkward = types_module.PaneTarget(
        backend="herdr",
        socket_path=tmp_path / "a dir: with colons" / "herdr.sock",
        server_generation="1:2:3",
        pane_id="w1:p1",
        terminal_id="term_x",
    )
    forging = types_module.PaneTarget(
        backend="herdr",
        socket_path=tmp_path / "a dir",
        server_generation=": with colons/herdr.sock:1:2:3",
        pane_id="w1:p1",
        terminal_id="term_x",
    )
    assert awkward.identity != forging.identity
    # Six fields exactly: the kind plus the five escaped components. A
    # component that leaked a separator would produce more.
    assert len(awkward.identity.split(":")) == 6
    assert len(forging.identity.split(":")) == 6
    assert awkward.kind == "herdr-pane"
    assert awkward.record_payload()["identity"] == awkward.identity
    assert awkward.record_payload()["kind"] == "herdr-pane"


def test_a_registered_pane_target_round_trips_through_its_record(
    *,
    tmp_path: Path,
) -> None:
    """Inventory reconstructs a pane target, not a gate target, from a record."""
    routing = _module(name="_session_wait_routing")
    types_module = _module(name="_session_wait_types")
    pane_target = types_module.PaneTarget(
        backend="herdr",
        socket_path=tmp_path / "herdr.sock",
        server_generation="7:8:9",
        pane_id="w2:p3",
        terminal_id="term_round",
    )
    assert routing.wait_target_from_payload(payload=pane_target.record_payload()) == pane_target
    gate_target = types_module.GateTarget(
        gate_store_root=tmp_path / "gate-runs",
        run_id="run-1",
        generation="gen-1",
    )
    assert routing.wait_target_from_payload(payload=gate_target.record_payload()) == gate_target
    assert gate_target.kind == "gate"


def test_routing_sends_each_target_kind_to_its_own_adapter(*, tmp_path: Path) -> None:
    routing = _module(name="_session_wait_routing")
    pane_module = _module(name="_session_wait_pane")
    types_module = _module(name="_session_wait_types")
    gate_module = _module(name="_session_wait_gate")
    launcher = routing.default_wait_launcher(repository=tmp_path)
    pane_target = types_module.PaneTarget(
        backend="herdr",
        socket_path=tmp_path / "herdr.sock",
        server_generation="1:1:1",
        pane_id="w1:p1",
        terminal_id="term_route",
    )
    gate_target = types_module.GateTarget(
        gate_store_root=tmp_path / "gate-runs",
        run_id="run-route",
        generation="gen-route",
    )
    gate_probe = launcher.launch(target=gate_target, timeout_seconds=1.0)
    assert isinstance(gate_probe, gate_module.GateStatusProbe)
    gate_probe.cancel(timeout_seconds=5.0)
    # The pane probe answers on its OWN worker, so the point here is that it
    # answers at all through whatever scheduling it uses, rather than what the
    # answer says — and a read that never completes is what makes the wait for
    # it the worker's own exit instead of a guess. The peer is bound and never
    # accepts, so the read blocks for its whole budget; see `_hanging_peer`.
    herdr_module = _module(name="_session_wait_herdr")
    with _hanging_peer(name="routing-probe.sock") as hanging_socket:
        hanging_pane = types_module.PaneTarget(
            backend="herdr",
            socket_path=hanging_socket,
            server_generation=str(herdr_module.herdr_socket_generation(socket_path=hanging_socket)),
            pane_id="w1:p1",
            terminal_id="term_route_hanging",
        )
        pane_probe = launcher.launch(
            target=hanging_pane,
            timeout_seconds=_HANGING_BUDGET_SECONDS,
        )
        assert isinstance(pane_probe, pane_module.HerdrPaneProbe)
        observed = _observed_through_its_own_worker(probe=pane_probe)
        # The read timed out, so the probe reports a DIAGNOSTIC: nothing about
        # the pane was measured, and naming a state would be a claim nobody made.
        assert observed.state not in _PANE_STATES
    pane_probe.cancel(timeout_seconds=5.0)
    # The default observer routes the same way, through each kind's own
    # adapter. The pane's socket does not exist and the gate store holds no
    # `started_at`, so both answers are diagnostics rather than states.
    assert routing.observe_wait_target(target=pane_target, observed_at=2.0).state not in (
        _PANE_STATES
    )
    gate_observation = routing.observe_wait_target(target=gate_target, observed_at=1.0)
    assert gate_observation.state == "GONE"
    assert types_module.observation_is_running(observation=gate_observation) is False
    assert (
        types_module.observation_is_running(
            observation=types_module.GateObservation.running(
                target=gate_target,
                observed_at=1.0,
            )
        )
        is True
    )


def test_a_wait_demands_at_least_one_target(*, tmp_path: Path) -> None:
    """Arming with no target at all is a usage error, not an empty wait."""
    session_wait = _module(name="session_wait")
    seams = _cli_seams(repository=tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _ = session_wait.main(
            argv=[
                "wait",
                "--repo",
                str(tmp_path),
                "--session-id",
                "pane-session",
                "--wait-id",
                "no-targets",
                "--deadline-seconds",
                "5",
            ],
            seams=seams,
        )
    assert excinfo.value.code == 2


def _malformed_replies() -> list[tuple[str, bytes]]:
    """Each protocol failure a healthy server cannot be asked to produce."""
    return [
        ("truncated", b"{not json at all}\n"),
        ("not-an-object", b"[1, 2, 3]\n"),
        ("target-absent-error", b'{"id":"test","error":{"code":"agent_not_found"}}\n'),
        # A named server error that is NOT about the target: the measurement
        # failed, which is a different end from the pane being absent.
        ("server-side-error", b'{"id":"test","error":{"code":"server_unavailable"}}\n'),
        ("unnamed-error", b'{"id":"test","error":{"code":17}}\n'),
        ("no-agent-record", b'{"id":"test","result":{"type":"agent_info"}}\n'),
        ("agent-without-identity", _agent_reply(agent={"pane_id": "w1:p1"})),
        ("closed-without-reply", b""),
        # No newline in two megabytes: the reply ceiling stops the read, and
        # the truncated buffer does not parse.
        ("over-the-reply-ceiling", b"x" * (2 << 20)),
    ]


def test_a_pane_target_cannot_be_armed_against_an_unobservable_server(
    *,
    tmp_path: Path,
) -> None:
    """A pane whose identity cannot be read is refused at arm time.

    Refusing HERE rather than arming is what keeps a wait from blocking for
    its whole deadline against a pane that was never there, and the cases
    below are CONTROLLED PEERS, disclosed as such.
    """
    pane_module = _module(name="_session_wait_pane")
    herdr_module = _module(name="_session_wait_herdr")

    # An absent socket has no generation at all, which is what keeps a target
    # from being armed against a server that is not there.
    missing = tmp_path / "absent.sock"
    assert herdr_module.herdr_socket_generation(socket_path=missing) is None
    with pytest.raises(FileNotFoundError):
        _ = pane_module.freeze_pane_target(socket_path=missing, pane_id="w1:p1")

    # A path that exists but is not a socket: the generation reads, the
    # connection cannot be made, and that is a transport failure rather than
    # a verdict about any pane.
    not_a_socket = tmp_path / "regular-file"
    _ = not_a_socket.write_text("not a socket\n", encoding="utf-8")
    assert herdr_module.herdr_socket_generation(socket_path=not_a_socket) is not None
    with pytest.raises(ValueError, match="not identifiable"):
        _ = pane_module.freeze_pane_target(socket_path=not_a_socket, pane_id="w1:p1")

    for label, reply in _malformed_replies():
        with (
            _controlled_peer(name=f"arm-{label}.sock", replies=[reply]) as peer_path,
            pytest.raises(ValueError, match="not identifiable"),
        ):
            _ = pane_module.freeze_pane_target(
                socket_path=peer_path,
                pane_id="w1:p1",
                timeout_seconds=10.0,
            )


def test_a_pane_observation_never_fabricates_a_pane_state() -> None:
    """Every unreadable, unreachable or absent answer stays out of the state set.

    These are the paths where an adapter most easily invents a plausible
    state, so the control at the end matters as much as the cases: it proves
    the assertions are not passing for want of a success path.
    """
    pane_module = _module(name="_session_wait_pane")
    herdr_module = _module(name="_session_wait_herdr")
    types_module = _module(name="_session_wait_types")
    for label, reply in _malformed_replies():
        with _controlled_peer(name=f"observe-{label}.sock", replies=[reply]) as peer_path:
            target = types_module.PaneTarget(
                backend="herdr",
                socket_path=peer_path,
                server_generation=str(herdr_module.herdr_socket_generation(socket_path=peer_path)),
                pane_id="w1:p1",
                terminal_id="term_test",
            )
            observation = pane_module.observe_pane_target(target=target, observed_at=5.0)
            assert observation.state not in _PANE_STATES, label
            assert observation.fresh is True
            assert observation.exit_code is None
            assert types_module.observation_is_running(observation=observation) is False, label

    # A record that parses but reports no usable status is the same class of
    # answer: there is no state to return, so none is invented.
    with _controlled_peer(
        name="status-free.sock",
        replies=[_agent_reply(agent={"terminal_id": "term_test"})],
    ) as status_free:
        target = pane_module.freeze_pane_target(socket_path=status_free, pane_id="w1:p1")
        assert target.terminal_id == "term_test"
        unusable = pane_module.observe_pane_target(target=target, observed_at=6.0)
        assert unusable.state not in _PANE_STATES

    # The control: a well-formed record IS returned verbatim.
    with _controlled_peer(
        name="healthy.sock",
        replies=[_agent_reply(agent={"terminal_id": "term_test", "agent_status": "blocked"})],
    ) as healthy:
        target = pane_module.freeze_pane_target(socket_path=healthy, pane_id="w1:p1")
        observation = pane_module.observe_pane_target(target=target, observed_at=7.0)
        assert observation.state == "blocked"
        assert types_module.observation_is_running(observation=observation) is False


def test_a_server_replaced_at_the_same_path_ends_with_its_own_outcome() -> None:
    """A frozen identity does not follow its socket path onto another server.

    The generation a pane target freezes is its server's socket identity, and
    a server restarted at the same path binds a new one. This reaches the
    REPLACED arm without a herdr binary: the peer answers with a perfectly
    plausible agent record, and the target carries a generation that peer's
    socket never had — which is exactly what a replaced server looks like to a
    frozen target. The plausible record is the point: asking the pane first
    would return its state, so the outcome proves the server is asked first.
    """
    pane_module = _module(name="_session_wait_pane")
    herdr_module = _module(name="_session_wait_herdr")
    types_module = _module(name="_session_wait_types")
    with _controlled_peer(
        name="replaced.sock",
        replies=[_agent_reply(agent={"terminal_id": "term_test", "agent_status": "idle"})],
    ) as peer_path:
        live_generation = herdr_module.herdr_socket_generation(socket_path=peer_path)
        target = types_module.PaneTarget(
            backend="herdr",
            socket_path=peer_path,
            server_generation=f"{live_generation}-before-restart",
            pane_id="w1:p1",
            terminal_id="term_test",
        )
        observation = pane_module.observe_pane_target(target=target, observed_at=7.0)
    assert observation.state == pane_module.DIAGNOSTIC_REPLACED
    assert observation.state not in _PANE_STATES
    assert types_module.observation_is_running(observation=observation) is False
