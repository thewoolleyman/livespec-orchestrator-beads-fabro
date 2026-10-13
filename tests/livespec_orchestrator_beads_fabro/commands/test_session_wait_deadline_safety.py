"""Real deadline and probe-cancellation safety for bounded session waits."""

from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_herdr import (
    DIAGNOSTIC_UNAVAILABLE,
    herdr_socket_generation,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import ProbeLauncher
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    PaneTarget,
    RoutingLauncher,
    WaitRequest,
    run_wait,
)

# Long enough that a wait which serialized behind the hung probe could only
# return at expiry, so the two behaviours are separated by many seconds rather
# than by a margin that load could close.
_HUNG_DEADLINE_SECONDS = 20.0
_FINISHED_GATE_EXIT_CODE = 7
# `/bin/sh` rather than this interpreter: the gate launcher caps a probe's own
# budget at one second, and a cold Python start under coverage can exceed that
# — which would make this fixture's gate look unfinished for reasons that have
# nothing to do with the behaviour under test. The trailing word is `sh -c`'s
# `$0`, so the run id the probe appends lands in `$1` and is ignored.
_FINISHED_GATE_COMMAND = (
    "/bin/sh",
    "-c",
    f'printf "  state             : PASSED\\n  exit_code         : {_FINISHED_GATE_EXIT_CODE}\\n"',
    "finished-gate-status",
)
_PEER_RECEIVE_BYTES = 65536
# The lone-hung-pane wait below. Short, because what it asserts is the OUTCOME
# LABEL rather than a duration, and the race that decided that label is
# reproduced by the sleeper rather than waited for.
_LONE_DEADLINE_SECONDS = 0.4
# How far past the budget it was asked for `_overshooting_sleeper` really
# sleeps. It has to exceed a probe's launch latency — the few milliseconds
# between a round starting its worker and that worker reaching its `recv` —
# so the round that observes expiry reliably lands after the probe's own
# budget would have expired.
_POLL_OVERSHOOT_SECONDS = 0.8
# Repeated runs of ONE request, because the defect was an unstable label
# rather than a wrong one: the same wait reported `target-ended` and then
# `deadline` on two consecutive runs.
_LONE_RUNS = 2


def _hung_pane(*, socket_path: Path, terminal_id: str) -> PaneTarget:
    """A pane target whose SERVER identity matches the peer holding the socket.

    The generation is read from the peer's own socket file. A mismatched one is
    answered by the identity arm before any connection is attempted, which is a
    different end entirely and would let a case pass without the transport
    being exercised at all.
    """
    return PaneTarget(
        backend="herdr",
        socket_path=socket_path,
        server_generation=str(herdr_socket_generation(socket_path=socket_path)),
        pane_id="w1:p1",
        terminal_id=terminal_id,
    )


def _overshooting_sleeper(*, seconds: float) -> None:
    """Sleep the budget the wait asked for, plus the overshoot that decides it.

    `time.sleep` overshoots on its own, and the measured race turned on exactly
    that: the poll round that observes expiry runs a little AFTER the deadline,
    so whether it ALSO sees the hung probe's timeout diagnostic is settled by
    microseconds nobody controls. Overshooting deliberately, by far more than a
    probe's launch latency, makes that round see the diagnostic on every run —
    so a wait that can still report a hung probe as a finished target reports
    it here every time instead of half the time.
    """
    time.sleep(seconds + _POLL_OVERSHOOT_SECONDS)


def _written_pid(*, path: Path, timeout_seconds: float) -> int:
    """One pid, read only once its writer has finished writing it.

    The condition is NON-EMPTY CONTENT rather than mere existence, and that is
    a race a caller cannot retry its way out of: `write_text` creates the file
    before its bytes land, so an existence-gated read can return `""` and the
    `int` of that raises `ValueError` — reporting a fixture race as a failure
    of the cancellation the test was actually asserting. Measured here once in
    four runs as soon as a sibling test put real load on the process, against
    six clean runs without it.
    """
    deadline = time.monotonic() + timeout_seconds
    content = ""
    while not content and time.monotonic() < deadline:
        with suppress(OSError):
            content = path.read_text(encoding="utf-8").strip()
        if not content:
            time.sleep(0.005)
    assert content, f"{path} never received a pid"
    return int(content)


@contextmanager
def _hung_peer(*, socket_path: Path) -> Iterator[list[bytes]]:
    """A unix socket that ACCEPTS and then never answers.

    Disclosed as a CONTROLLED PEER rather than presented as a server: a healthy
    Herdr server cannot be asked to hang, and what is under test here is what
    the WAIT does while one observation hangs, so hanging is the peer's whole
    job. Each accepted connection is held OPEN deliberately — closing it would
    end the probe's read with an empty buffer, which is a reply the probe can
    read and therefore not a hang at all.

    Every request it receives is recorded and yielded, so a test can assert
    which calls reached the target rather than assuming the adapter only reads.
    """
    received: list[bytes] = []
    held: list[socket.socket] = []
    stop = threading.Event()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.settimeout(0.05)

    def hold(*, connection: socket.socket) -> None:
        with suppress(OSError):
            connection.settimeout(1.0)
            received.append(connection.recv(_PEER_RECEIVE_BYTES))

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            held.append(connection)
            threading.Thread(
                target=hold,
                kwargs={"connection": connection},
                daemon=True,
            ).start()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield received
    finally:
        stop.set()
        worker.join(timeout=30.0)
        for connection in held:
            connection.close()
        listener.close()


def test_a_hung_pane_probe_lets_a_finished_gate_return_first(*, tmp_path: Path) -> None:
    """Scenario 156: a hung first probe does not serialize a finished sibling.

    The pane is listed FIRST and its peer never answers, so an adapter that
    observes a pane on the polling thread cannot reach the gate until that
    probe's own budget expires — and that budget is the whole remaining
    deadline. Measured against the synchronous adapter: the wait returned at
    20.03s of a 20s deadline, reporting the HUNG PANE's `UNAVAILABLE`
    diagnostic as the trigger while the gate that had already finished was
    reported as unfinished.

    The gate is driven by a scripted status command rather than a real gate
    run, because what this asserts is the WAIT's scheduling; the gate only has
    to be already finished when the wait starts.
    """
    gate_store_root = tmp_path / "gate-runs"
    gate_dir = gate_store_root / "finished-gate"
    gate_dir.mkdir(parents=True)
    _ = (gate_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    gate = GateTarget.freeze(gate_store_root=gate_store_root, run_id=gate_dir.name)
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "hung.sock"

    with _hung_peer(socket_path=socket_path) as received:
        pane = PaneTarget(
            backend="herdr",
            socket_path=socket_path,
            server_generation=str(herdr_socket_generation(socket_path=socket_path)),
            pane_id="w1:p1",
            terminal_id="term_hung",
        )
        started = time.monotonic()
        result = run_wait(
            request=WaitRequest(
                wait_id="hung-pane-first",
                session_id="deadline-safety",
                repository=tmp_path,
                deadline_seconds=_HUNG_DEADLINE_SECONDS,
                targets=(pane, gate),
            ),
            launcher=RoutingLauncher(
                gate=GateStatusLauncher(
                    repository=tmp_path,
                    command_prefix=_FINISHED_GATE_COMMAND,
                ),
                pane=HerdrPaneLauncher(),
            ),
            wait_store_root=wait_store_root,
        )
        elapsed = time.monotonic() - started

    # The finished gate is what woke the wait, carrying its OWN exit code.
    assert result.trigger_target == gate.identity
    assert result.command_outcome == "target-ended"
    assert result.trigger_exit_code == _FINISHED_GATE_EXIT_CODE
    assert pane.identity in result.unfinished_targets
    # Inside the ORIGINAL deadline and nowhere near it. A wait that polled the
    # hung pane on its own thread could only return once that probe's budget
    # expired, which is the entire deadline.
    assert elapsed < _HUNG_DEADLINE_SECONDS / 2, f"returned after {elapsed:.2f}s"
    # The hung target was READ and never written to, so the probe work that got
    # cancelled was this wait's own and nothing belonging to the pane.
    assert received, "the wait never reached the hung peer at all"
    for request in received:
        assert json.loads(request.decode("utf-8"))["method"] == "agent.get"


def test_a_lone_hung_pane_wait_returns_the_deadline_outcome_on_every_run(
    *,
    tmp_path: Path,
) -> None:
    """Scenario 156: a pane that never answers is UNFINISHED, never ended.

    Measured 2026-10-13 against the real wait CLI with a hung controlled peer:
    two consecutive runs of one 3-second lone-hung-pane wait returned
    `target-ended` with state `UNAVAILABLE` and then `deadline` with the same
    state, for the identical request. A pane probe's read budget was the
    remaining deadline, so its timeout diagnostic and the deadline arrived
    together and the label went to whichever the final poll round happened to
    see first — and `target-ended` reports a hung probe as a FINISHED target,
    naming a pane nobody observed as the thing that woke the wait.

    The timing was correct on both of those runs, so what is asserted here is
    the LABEL, the unfinished-target listing and the staleness of the reported
    observation, over repeated runs of one request.
    """
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "lone-hung.sock"
    endings: list[tuple[str, str | None, tuple[str, ...]]] = []
    stale_readings: list[tuple[str, bool, bool]] = []

    with _hung_peer(socket_path=socket_path) as received:
        pane = _hung_pane(socket_path=socket_path, terminal_id="term_lone")
        for run in range(_LONE_RUNS):
            started = time.monotonic()
            result = run_wait(
                request=WaitRequest(
                    wait_id=f"lone-hung-pane-{run}",
                    session_id="deadline-safety",
                    repository=tmp_path,
                    deadline_seconds=_LONE_DEADLINE_SECONDS,
                    targets=(pane,),
                ),
                launcher=RoutingLauncher(
                    gate=GateStatusLauncher(repository=tmp_path),
                    pane=HerdrPaneLauncher(),
                ),
                wait_store_root=wait_store_root,
                sleeper=_overshooting_sleeper,
            )
            observation = result.observations[pane.identity]
            endings.append(
                (result.command_outcome, result.trigger_target, result.unfinished_targets)
            )
            stale_readings.append(
                (
                    observation.state,
                    observation.fresh,
                    observation.observed_at >= started + _LONE_DEADLINE_SECONDS,
                )
            )

    assert endings == [("deadline", None, (pane.identity,))] * _LONE_RUNS
    # What an unfinished target owes: `UNAVAILABLE` says this wait measured no
    # state at all, `fresh=False` says the reading is not a current one, and
    # the timestamp is the expiry the wait returned at.
    assert stale_readings == [(DIAGNOSTIC_UNAVAILABLE, False, True)] * _LONE_RUNS
    # The hung target was READ and never written to, so the work that got
    # cancelled at expiry was this wait's own and nothing belonging to the pane.
    assert received, "the wait never reached the hung peer at all"
    for request in received:
        assert json.loads(request.decode("utf-8"))["method"] == "agent.get"


def test_waiting_for_a_file_that_never_appears_refuses_at_the_deadline(*, tmp_path: Path) -> None:
    """The wait POLLS to a bounded deadline and then refuses, rather than hanging.

    This is the other arm of `_written_pid`, and only this test can reach it.
    The probe below publishes its pid through a POSIX shell that starts in
    milliseconds, so the file is already there on the first condition check and
    the polling body is never entered — the arm that matters when a probe dies
    before publishing anything is the one that must still terminate. Elapsed
    time is asserted rather than left to a coverage report, so a loop that
    stopped waiting (or never waited) fails here instead of passing silently.
    """
    started = time.monotonic()

    with pytest.raises(AssertionError):
        _ = _written_pid(path=tmp_path / "never-written", timeout_seconds=0.05)

    assert time.monotonic() - started >= 0.05


def test_registration_lock_is_inside_the_original_deadline(*, tmp_path: Path) -> None:
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    returned = threading.Event()
    result_outcomes: list[str] = []

    def invoke_wait() -> None:
        result = run_wait(
            request=WaitRequest(
                wait_id="lock-bound",
                session_id="deadline-safety",
                repository=tmp_path,
                deadline_seconds=0.05,
                targets=(),
            ),
            launcher=cast("ProbeLauncher", object()),
            wait_store_root=wait_store_root,
        )
        result_outcomes.append(result.command_outcome)
        returned.set()

    lock_path = wait_store_root / ".inventory.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        worker = threading.Thread(target=invoke_wait)
        worker.start()
        returned_by_bound = returned.wait(timeout=0.2)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    worker.join(timeout=1.0)

    assert returned_by_bound is True
    assert result_outcomes == ["deadline"]
    assert worker.is_alive() is False


def test_cancelling_probe_terminates_probe_child_only(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    gate_dir = gate_store_root / "synthetic-gate"
    gate_dir.mkdir(parents=True)
    _ = (gate_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=gate_store_root, run_id=gate_dir.name)
    pid_file = tmp_path / "probe.pid"
    # A POSIX-SHELL probe rather than a Python one, because `launch` clamps its
    # budget to `min(1.0, ...)` and a cold CPython cannot reach its first
    # statement inside one second while the suite runs under coverage tracing
    # on a loaded host — the probe was reaped before it ever published its pid,
    # so this test failed on its pid wait for a reason that was never about
    # the code under test. The semantics it asserts are preserved exactly: the
    # trap is armed BEFORE the pid is published, so SIGTERM is already ignored
    # by the time the test can read the pid; `exec` then replaces the shell in
    # place, so the published pid stays the live process's own pid and process
    # group, and an ignored disposition survives `exec` per POSIX. Cancellation
    # must therefore still escalate past SIGTERM to kill it.
    helper = tmp_path / "sleeping-probe.sh"
    _ = helper.write_text(
        """trap '' TERM
echo $$ > "$1"
exec sleep 30
""",
        encoding="utf-8",
    )
    probe = GateStatusLauncher(
        repository=tmp_path,
        command_prefix=("/bin/sh", str(helper), str(pid_file)),
    ).launch(target=target, timeout_seconds=1.0)
    assert probe.poll(now=time.monotonic()) is None
    probe_pid = _written_pid(path=pid_file, timeout_seconds=5.0)

    probe.cancel(timeout_seconds=0.05)
    time.sleep(0.1)
    probe_alive = Path(f"/proc/{probe_pid}").exists()
    with suppress(ProcessLookupError):
        os.kill(probe_pid, signal.SIGKILL)
    assert probe_alive is False
    assert probe.active is False
    assert (gate_dir / "started_at").read_text(encoding="utf-8") == "generation-one\n"
