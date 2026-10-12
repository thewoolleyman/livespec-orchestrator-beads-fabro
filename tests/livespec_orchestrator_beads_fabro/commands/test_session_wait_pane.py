"""Herdr pane targets observed by the bounded host-session wait.

Scenario 155 of `SPECIFICATION/scenarios.md` governs this module: only a
`working` pane continues a wait, and every other state ends it with the actual
observed state or a distinct diagnostic outcome.

TWO CLASSES OF PEER ARE USED HERE, and the difference is disclosed rather than
blurred, because they prove different things.

A REAL ISOLATED HERDR SERVER (`_isolated_herdr_server`) is the behavioural
proof. It is a genuine `herdr server` process, bound to its own socket under
its own XDG config root, holding its own workspaces, and it is driven through
the same `pane.report_agent` lifecycle surface a real agent integration uses.
Nothing in it is simulated, and it is torn down by process group so no server
outlives its test. It is SKIPPED where `herdr` is not installed, so the suite
still runs on a host without that capability; every branch of the adapter is
reachable without it.

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
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import pytest

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"

# Every state a Herdr pane can report. A diagnostic must never be rendered as
# one of these: an unreadable reply presented as `unknown` would turn "this
# probe failed" into "the server reports the agent's state as uncertain",
# which is a claim about the agent that nobody measured.
_PANE_STATES = frozenset({"working", "idle", "done", "blocked", "unknown"})

# `sizeof(sun_path)` is 108 bytes including the terminator on Linux, and
# `herdr-client.sock` is the longer of the two sockets herdr binds.
_SUN_PATH_LIMIT = 107
_LONGEST_HERDR_SOCKET_NAME = "herdr-client.sock"

_requires_herdr = pytest.mark.skipif(
    shutil.which("herdr") is None,
    reason="the herdr sandbox capability is not installed on this host",
)


def _module(*, name: str) -> object:
    """One session-wait module, imported inside the test body.

    The import is deliberately NOT at module top: the Red moment of this
    slice runs the pane behaviour against minimal failing stubs of the new
    adapter modules, and a top-level import would turn a later absence into a
    collection error — which proves only unimportability, not that the
    behaviour is unimplemented.
    """
    return importlib.import_module(f"{_COMMANDS}.{name}")


@dataclass(kw_only=True)
class _HerdrServer:
    socket_path: Path

    def call(self, *, method: str, params: dict[str, object]) -> dict[str, object]:
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        channel.settimeout(30.0)
        try:
            channel.connect(str(self.socket_path))
            request = {"id": "test", "method": method, "params": params}
            channel.sendall(json.dumps(request).encode("utf-8") + b"\n")
            line = channel.makefile("rb").readline()
        finally:
            channel.close()
        return json.loads(line.decode("utf-8"))

    def workspace_pane(self, *, label: str, focus: bool) -> str:
        """The root pane of a new workspace, focused or not as asked.

        FOCUS DECIDES WHICH STATES ARE REACHABLE, which is why it is a
        parameter rather than a detail. Herdr derives `done` from a completed
        turn nobody has looked at, so the SAME reported transition
        (`working` then `idle`) lands differently: measured on herdr 0.9.3, a
        focused pane reports `idle` and an unfocused one reports `done` with a
        `completion_seq`. Neither state is reachable on the other pane, so a
        test asserting both needs one of each.
        """
        created = self.call(
            method="workspace.create",
            params={"cwd": "/tmp", "label": label, "focus": focus},
        )
        assert "result" in created, f"workspace.create failed: {created}"
        return str(created["result"]["root_pane"]["pane_id"])

    def report(self, *, pane_id: str, state: str) -> None:
        _ = self.call(
            method="pane.report_agent",
            params={
                "pane_id": pane_id,
                "agent": "claude",
                "source": "livespec-session-wait-test",
                "state": state,
            },
        )

    def agent_status(self, *, pane_id: str) -> str:
        observed = self.call(method="agent.get", params={"target": pane_id})
        return str(observed["result"]["agent"]["agent_status"])

    def await_status(self, *, pane_id: str, state: str) -> None:
        observed = ""
        deadline = time.monotonic() + 30.0
        while observed != state and time.monotonic() < deadline:
            observed = self.agent_status(pane_id=pane_id)
            time.sleep(0.05)
        assert observed == state, f"pane {pane_id} settled at {observed!r}, not {state!r}"

    def session_is_live(self) -> bool:
        """Whether this server's SESSION actor answers, not just its socket.

        `ping` is the wrong readiness gauge and this is the whole reason the
        method exists: it is answered by the transport before the session
        actor exists. Measured on herdr 0.9.3 under load, `ping` answered at
        ~0.12s while `session.snapshot` only answered 0.6-1.1s later, and a
        `workspace.create` issued in that window is refused with
        `server_unavailable` / "receiving on a closed channel". A fixture
        gated on `ping` therefore hands out a server that cannot yet hold a
        workspace, which presents as a flaky KeyError on the reply.
        """
        with suppress(OSError, json.JSONDecodeError):
            return "result" in self.call(method="session.snapshot", params={})
        return False


def _tail(*, path: Path, limit: int = 2000) -> str:
    """The end of one log, or an explicit note that it does not exist."""
    if not path.is_file():
        return f"<{path} absent>"
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def _readiness_diagnostic(
    *,
    socket_path: Path,
    process: subprocess.Popen[bytes],
    launch_log: Path,
    server_log: Path,
) -> str:
    """Why a server never became session-live, in enough detail to act on.

    An expiry here is reported with the SERVER'S OWN output rather than as a
    bare timeout, because the two causes need opposite responses: a process
    that exited is a launch failure whose reason is in its log, while a live
    process that never answered is a readiness-gauge or load problem.
    """
    return (
        f"the isolated herdr server at {socket_path} never became session-live"
        f"\n  socket present: {socket_path.exists()}"
        f"\n  process returncode: {process.poll()}"
        f"\n  launch log: {_tail(path=launch_log)}"
        f"\n  server log: {_tail(path=server_log)}"
    )


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


@contextmanager
def _isolated_herdr_server(*, directory: Path):
    """A real herdr server bound under one owned short root.

    The `sun_path` bound is ASSERTED rather than assumed, so a future rename
    that lengthens the path fails loudly and once instead of flaking per
    worker.
    """
    config = directory / "c"
    config.mkdir(parents=True, exist_ok=True)
    # Every inherited `HERDR_*` variable is DROPPED, because a run launched from
    # inside a herdr pane carries `HERDR_SOCKET_PATH`, which the server honours
    # over the XDG roots: measured on the host, the "isolated" server found the
    # operator's live socket, printed `herdr server is already running` and
    # exited 1. The factory sandbox carries no such variable, so only a host
    # run exposed it — and an inherited socket path aims at a server this
    # fixture does not own.
    environment = dict(
        {name: value for name, value in os.environ.items() if not name.startswith("HERDR_")},
        XDG_CONFIG_HOME=str(config),
        XDG_DATA_HOME=str(directory / "d"),
        XDG_STATE_HOME=str(directory / "s"),
    )
    socket_path = config / "herdr" / "herdr.sock"
    longest = config / "herdr" / _LONGEST_HERDR_SOCKET_NAME
    assert len(str(longest)) <= _SUN_PATH_LIMIT, (
        f"{longest} is {len(str(longest))} bytes, over the {_SUN_PATH_LIMIT}-byte"
        " sun_path limit; herdr would exit before binding"
    )
    launch_log = directory / "launch.log"
    with launch_log.open("wb") as sink:
        process = subprocess.Popen(
            ["herdr", "server"],
            env=environment,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        server = _HerdrServer(socket_path=socket_path)
        # BOUNDED, and the bound FAILS rather than yielding an unready server.
        # Readiness is the session actor answering, never the socket merely
        # existing or `ping` replying — see `session_is_live`.
        live = False
        deadline = time.monotonic() + 90.0
        while not live and time.monotonic() < deadline:
            live = socket_path.exists() and server.session_is_live()
            time.sleep(0.02)
        assert live, _readiness_diagnostic(
            socket_path=socket_path,
            process=process,
            launch_log=launch_log,
            server_log=config / "herdr" / "herdr-server.log",
        )
        yield server
    finally:
        # By process GROUP, because `herdr server` is started in its own
        # session: killing the parent alone can leave the bound socket and its
        # workspaces behind, and the next test would then observe a server
        # this one owned.
        with suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        _ = process.wait(timeout=90)


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


def _wait_argv(
    *,
    repository: Path,
    wait_id: str,
    socket_path: Path,
    pane_id: str,
    deadline_seconds: str,
) -> list[str]:
    return [
        "wait",
        "--repo",
        str(repository),
        "--session-id",
        "pane-session",
        "--wait-id",
        wait_id,
        "--deadline-seconds",
        deadline_seconds,
        "--pane",
        str(socket_path),
        pane_id,
    ]


def _poll_until_observed(*, probe: object):
    """One observation from a probe, however it schedules its own work."""
    observation = None
    deadline = time.monotonic() + 30.0
    while observation is None and time.monotonic() < deadline:
        observation = probe.poll(now=time.monotonic())
        time.sleep(0.01)
    assert observation is not None, "the probe never produced an observation"
    return observation


def _run_pane_wait(
    *,
    server: _HerdrServer,
    repository: Path,
    wait_id: str,
    pane_id: str,
    deadline_seconds: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, object]]:
    session_wait = _module(name="session_wait")
    exit_code = session_wait.main(
        argv=_wait_argv(
            repository=repository,
            wait_id=wait_id,
            socket_path=server.socket_path,
            pane_id=pane_id,
            deadline_seconds=deadline_seconds,
        ),
        seams=_cli_seams(repository=repository),
    )
    return exit_code, json.loads(capsys.readouterr().out)


def _frozen_pane_targets(*, server: _HerdrServer, pane_ids: tuple[str, ...]) -> dict[str, object]:
    pane_module = _module(name="_session_wait_pane")
    targets: dict[str, object] = {}
    for pane_id in pane_ids:
        server.report(pane_id=pane_id, state="working")
        server.await_status(pane_id=pane_id, state="working")
        targets[pane_id] = pane_module.freeze_pane_target(
            socket_path=server.socket_path,
            pane_id=pane_id,
        )
    return targets


@_requires_herdr
def test_a_pane_wait_returns_the_actual_non_working_state(
    *,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 155: only `working` continues; every other state is returned.

    The states are driven on a REAL isolated herdr server, and each one is
    confirmed through that server's own `agent.get` before the wait runs, so a
    returned state is the state the server actually held rather than the state
    this test assumed it had set.
    """
    with _short_root() as directory, _isolated_herdr_server(directory=directory) as server:
        # One focused pane and one unfocused pane, because focus decides which
        # states the server can reach at all — see `workspace_pane`.
        focused = server.workspace_pane(label="focused", focus=True)
        unfocused = server.workspace_pane(label="unfocused", focus=False)
        targets = _frozen_pane_targets(server=server, pane_ids=(focused, unfocused))
        assert targets[focused].backend == "herdr"
        assert targets[focused].pane_id == focused

        working_code, working_payload = _run_pane_wait(
            server=server,
            repository=tmp_path,
            wait_id="pane-working",
            pane_id=focused,
            deadline_seconds="3",
            capsys=capsys,
        )
        identity = targets[focused].identity
        assert working_code == 0
        assert working_payload["command_outcome"] == "deadline"
        assert working_payload["unfinished_targets"] == [identity]
        assert working_payload["observations"][identity]["state"] == "working"

        # `done` is the server's OWN derivation of a completed turn, reached by
        # reporting `idle` on an UNFOCUSED pane; `idle` is the same report on a
        # focused one. `done` is not a reportable lifecycle state at all.
        cases = (
            ("idle", focused, "idle"),
            ("done", unfocused, "idle"),
            ("blocked", focused, "blocked"),
            ("unknown", focused, "unknown"),
        )
        for index, (state, pane_id, reported) in enumerate(cases):
            server.report(pane_id=pane_id, state="working")
            server.await_status(pane_id=pane_id, state="working")
            server.report(pane_id=pane_id, state=reported)
            server.await_status(pane_id=pane_id, state=state)
            exit_code, payload = _run_pane_wait(
                server=server,
                repository=tmp_path,
                wait_id=f"pane-{state}-{index}",
                pane_id=pane_id,
                deadline_seconds="30",
                capsys=capsys,
            )
            target_identity = targets[pane_id].identity
            assert exit_code == 0
            assert payload["command_outcome"] == "target-ended"
            assert payload["trigger_target"] == target_identity
            assert payload["observations"][target_identity]["state"] == state
            assert payload["observations"][target_identity]["fresh"] is True
            # The command's outcome stays separate from the target's verdict:
            # a pane carries no exit code, and `target-ended` is not one.
            assert payload["trigger_exit_code"] is None


@_requires_herdr
def test_a_frozen_pane_identity_binds_its_server_instance() -> None:
    """A reused pane id cannot alias a pane on another Herdr server."""
    pane_module = _module(name="_session_wait_pane")
    identities: list[str] = []
    pane_ids: list[str] = []
    for _ in range(2):
        with _short_root() as directory, _isolated_herdr_server(directory=directory) as server:
            pane_id = server.workspace_pane(label="alias", focus=True)
            server.report(pane_id=pane_id, state="working")
            server.await_status(pane_id=pane_id, state="working")
            target = pane_module.freeze_pane_target(
                socket_path=server.socket_path,
                pane_id=pane_id,
            )
            identities.append(target.identity)
            pane_ids.append(target.pane_id)
    # The two servers minted the SAME pane id, which is what makes this an
    # aliasing test rather than a test of two different ids.
    assert pane_ids[0] == pane_ids[1]
    assert identities[0] != identities[1]


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
    pane_probe = launcher.launch(target=pane_target, timeout_seconds=1.0)
    gate_probe = launcher.launch(target=gate_target, timeout_seconds=1.0)
    assert isinstance(pane_probe, pane_module.HerdrPaneProbe)
    assert isinstance(gate_probe, gate_module.GateStatusProbe)
    # The pane's socket does not exist, so this observation is a diagnostic —
    # the point here is that the probe answers at all, through whatever
    # scheduling it uses, rather than what the answer says.
    assert _poll_until_observed(probe=pane_probe).state not in _PANE_STATES
    pane_probe.cancel(timeout_seconds=5.0)
    gate_probe.cancel(timeout_seconds=5.0)
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


@_requires_herdr
def test_a_missing_pane_and_a_changed_server_end_with_distinct_outcomes() -> None:
    """Scenario 155: each uncertain end has its OWN outcome, not one shared one.

    The three ends a wait can reach other than a reported state are a pane
    that is GONE from a live server, a server that was REPLACED under the
    frozen identity, and a reply that could not be READ. They are asserted
    PAIRWISE DISTINCT rather than merely non-success: one shared diagnostic
    satisfies every "is not a state" check while telling an operator nothing
    about which of three different repairs applies.

    The missing-pane and changed-generation cases run on a REAL herdr server
    — the generation case by restarting one at the SAME socket path, which is
    the only way the path itself does not change. Only the unreadable case
    uses a controlled peer, because no healthy server will truncate its own
    reply.
    """
    pane_module = _module(name="_session_wait_pane")
    outcomes: dict[str, str] = {}
    with _short_root() as directory:
        with _isolated_herdr_server(directory=directory) as first:
            pane_id = first.workspace_pane(label="distinct", focus=True)
            first.report(pane_id=pane_id, state="working")
            first.await_status(pane_id=pane_id, state="working")
            frozen = pane_module.freeze_pane_target(
                socket_path=first.socket_path,
                pane_id=pane_id,
            )
            # A live server that no longer holds the pane: the server answers,
            # and its answer is that this target is gone.
            _ = first.call(method="pane.close", params={"pane_id": pane_id})
            outcomes["missing"] = pane_module.observe_pane_target(
                target=frozen,
                observed_at=1.0,
            ).state
        # The socket is gone with its server, which is a different end again.
        outcomes["socket-gone"] = pane_module.observe_pane_target(
            target=frozen,
            observed_at=2.0,
        ).state
        # A DIFFERENT server instance at the SAME socket path. The frozen
        # identity must not follow the path onto it, however plausible the
        # pane id it happens to mint.
        with _isolated_herdr_server(directory=directory) as second:
            reused = second.workspace_pane(label="distinct", focus=True)
            assert reused == frozen.pane_id, "the restart did not reuse the pane id"
            outcomes["generation-changed"] = pane_module.observe_pane_target(
                target=frozen,
                observed_at=3.0,
            ).state

    with _controlled_peer(
        name="unreadable.sock",
        replies=[b"{not json}\n"],
    ) as unreadable_path:
        herdr_module = _module(name="_session_wait_herdr")
        types_module = _module(name="_session_wait_types")
        unreadable_target = types_module.PaneTarget(
            backend="herdr",
            socket_path=unreadable_path,
            server_generation=str(
                herdr_module.herdr_socket_generation(socket_path=unreadable_path)
            ),
            pane_id="w1:p1",
            terminal_id="term_test",
        )
        outcomes["unreadable"] = pane_module.observe_pane_target(
            target=unreadable_target,
            observed_at=4.0,
        ).state

    assert set(outcomes) == {"missing", "socket-gone", "generation-changed", "unreadable"}
    for label, state in outcomes.items():
        assert state not in _PANE_STATES, f"{label} was reported as a pane state: {state}"
    # PAIRWISE distinct, which is the whole assertion: a single shared
    # diagnostic would pass every check above.
    assert len(set(outcomes.values())) == len(outcomes), outcomes


def test_a_readiness_failure_reports_the_servers_own_cause(*, tmp_path: Path) -> None:
    """An unready server is reported with the evidence that discriminates why.

    This exercises the fixture's own diagnostic directly, because a green run
    never reaches it. It is worth testing rather than merely writing: a
    process that EXITED is a launch failure whose reason is in its own log —
    the `sun_path` overflow this fixture is bounded against is exactly that
    shape — while a live process that never answered is a readiness-gauge or
    load problem. A bare timeout cannot tell those apart, and an absent log
    has to say it is absent rather than read as an empty one.
    """
    absent = tmp_path / "gone.sock"
    # No socket to connect to, so the probe raises and is reported as not
    # live rather than escaping the fixture.
    assert _HerdrServer(socket_path=absent).session_is_live() is False
    launch_log = tmp_path / "launch.log"
    _ = launch_log.write_text(
        'Error: Custom { kind: InvalidInput, error: "local socket name length exceeds capacity of sun_path of sockaddr_un" }\n',
        encoding="utf-8",
    )
    # A REAL process that has really exited, so the diagnostic reports an exit
    # code it actually read. `true` rather than a Python child: an
    # instrumented Python subprocess races coverage collection, and this test
    # needs only something that terminates.
    exited = subprocess.Popen(["true"])
    _ = exited.wait(timeout=60)
    message = _readiness_diagnostic(
        socket_path=absent,
        process=exited,
        launch_log=launch_log,
        server_log=tmp_path / "never-written.log",
    )
    assert "never became session-live" in message
    assert "socket present: False" in message
    assert "process returncode: 0" in message
    assert "sun_path" in message
    assert "never-written.log absent" in message


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
