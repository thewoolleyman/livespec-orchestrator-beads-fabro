"""Real deadline and probe-cancellation safety for bounded session waits."""

from __future__ import annotations

import fcntl
import json
import os
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._session_wait_herdr import (
    DIAGNOSTIC_UNAVAILABLE,
    herdr_socket_generation,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import (
    HerdrPaneProbe,
    _PaneTask,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import ProbeLauncher
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateObservation,
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
_PEER_RECEIVE_BYTES = 65536
# The lone-hung-pane wait below. Short, because what it asserts is the OUTCOME
# LABEL rather than a duration, and the race that decided that label is
# reproduced by the sleeper rather than waited for.
_LONE_DEADLINE_SECONDS = 0.4
# How far past the budget it was asked for the settling sleeper advances the
# INJECTED clock. Any positive value puts the next round past expiry; the figure
# is kept well clear of zero so the overshoot is legible rather than marginal.
_POLL_OVERSHOOT_SECONDS = 0.8
# The instant every wait below is armed at, supplied through `WaitRequest` so
# the deadline is an exact number this module can assert against instead of a
# reading nobody controls.
_PINNED_START = 0.0
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


@dataclass(kw_only=True)
class _InjectedClock:
    """The monotonic clock a wait reads, advanced by this module and nobody else.

    It advances only through the sleeper handed alongside it, by exactly the
    seconds the wait asked to sleep — which is what the wait believes it slept
    — so a reading taken afterwards IS the budget that wait spent. That is what
    makes a budget assertion a statement about the poll loop rather than about
    the host: a clock advancing per READING would instead encode how many times
    the loop happens to look at it.
    """

    now: float = _PINNED_START

    def read(self) -> float:
        return self.now

    def sleep(self, *, seconds: float) -> None:
        self.now += seconds


def _settling_sleeper(
    *, clock: _InjectedClock, watcher: _WatchingPaneLauncher
) -> Callable[..., None]:
    """Let every in-flight pane read FINISH, then advance the clock past expiry.

    This is the deterministic replacement for a real sleep that overshot the
    deadline, and it reproduces the measured race rather than approximating it.
    Two things have to be true when the next round runs, and each now has its
    own mechanism instead of both riding on one duration:

    - The hung probe's own read must have ENDED, so a timeout diagnostic is
      genuinely available for a defective loop to mis-read as a finished
      target. That is the worker thread exiting, so the sleeper JOINS it — an
      event, not an interval. Without it the diagnostic does not exist yet, the
      defective loop finds nothing to mis-read, and the case passes against the
      very implementation it exists to refuse.
    - The deadline must have PASSED. That is arithmetic on the injected clock.

    The earlier sleeper slept `seconds + 0.8` in real time and hoped both had
    happened, which is why the label it graded was decided by microseconds.
    """

    def sleeper(*, seconds: float) -> None:
        for probe in watcher.probes:
            task = probe.inner.task
            # Asserted rather than branched on. Every probe here is mid-flight
            # when the loop sleeps — the poll that preceded it started the
            # worker and answered None — so a missing task is a changed adapter
            # to be reported, not a case to be skipped past silently.
            assert task is not None, "the probe started no observation"
            assert task.thread is not None, "the observation started no worker"
            task.thread.join()
        clock.sleep(seconds=seconds + _POLL_OVERSHOOT_SECONDS)

    return sleeper


def _reaching_sleeper(*, clock: _InjectedClock, reached: threading.Event) -> Callable[..., None]:
    """Wait until the probe's request has REACHED its peer, then expire the clock.

    A cancellation case has a precondition that an injected clock makes visible
    rather than creates: there is nothing to interrupt until the observation is
    genuinely blocked in `recv`, and under a real clock that was merely hoped
    for — the loop slept the deadline and the worker usually got there first.
    Here the peer's OWN receipt is the event, so the case establishes its
    precondition before the injected clock expires.
    """

    def sleeper(*, seconds: float) -> None:
        reached.wait()
        clock.sleep(seconds=seconds)

    return sleeper


@dataclass(kw_only=True)
class _WatchedPaneProbe:
    """One real pane probe, keeping the task each of its polls was serving.

    The task is what carries the read budget the observation is bounded by and
    the worker thread that observation runs on, and a probe RELEASES its task
    on cancellation — so neither survives the wait that used them. Recording
    them as the wait polls is the only way to read a wait's OWN probe rather
    than a reconstruction of it.
    """

    inner: HerdrPaneProbe
    tasks: list[_PaneTask | None] = field(default_factory=list)

    def poll(self, *, now: float) -> GateObservation | None:
        observation = self.inner.poll(now=now)
        self.tasks.append(self.inner.task)
        return observation

    def cancel(self, *, timeout_seconds: float) -> None:
        self.inner.cancel(timeout_seconds=timeout_seconds)


@dataclass(kw_only=True)
class _WatchingPaneLauncher:
    """The real pane launcher, keeping every probe it hands a wait."""

    probes: list[_WatchedPaneProbe] = field(default_factory=list)

    def launch(self, *, target: PaneTarget, timeout_seconds: float) -> _WatchedPaneProbe:
        probe = _WatchedPaneProbe(
            inner=HerdrPaneLauncher().launch(target=target, timeout_seconds=timeout_seconds),
        )
        self.probes.append(probe)
        return probe


def _listening_socket(*, socket_path: Path) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.settimeout(0.05)
    return listener


@contextmanager
def _hung_peer(
    *, socket_path: Path, on_receive: Callable[[], None] = lambda: None
) -> Iterator[list[bytes]]:
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
    listener = _listening_socket(socket_path=socket_path)

    def hold(*, connection: socket.socket) -> None:
        with suppress(OSError):
            connection.settimeout(1.0)
            received.append(connection.recv(_PEER_RECEIVE_BYTES))
            on_receive()

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

    The gate publishes its verdict once the hung peer has received its request.
    This handshake proves the slow observation is in flight before the gate ends.
    """
    gate_store_root = tmp_path / "gate-runs"
    gate_dir = gate_store_root / "finished-gate"
    gate_dir.mkdir(parents=True)
    _ = (gate_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    (gate_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    gate = GateTarget.freeze(gate_store_root=gate_store_root, run_id=gate_dir.name)
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "hung.sock"

    def complete_gate() -> None:
        partial = gate_dir / "exit_code.partial"
        partial.write_text(f"{_FINISHED_GATE_EXIT_CODE}\n", encoding="utf-8")
        partial.replace(gate_dir / "exit_code")

    with _hung_peer(socket_path=socket_path, on_receive=complete_gate) as received:
        pane = PaneTarget(
            backend="herdr",
            socket_path=socket_path,
            server_generation=str(herdr_socket_generation(socket_path=socket_path)),
            pane_id="w1:p1",
            terminal_id="term_hung",
        )
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
                ),
                pane=HerdrPaneLauncher(),
            ),
            wait_store_root=wait_store_root,
        )

    # The finished gate is what woke the wait, carrying its OWN exit code.
    # These four lines ARE the discriminator, and an elapsed bound that used to
    # sit beside them has been removed as corroboration that measured the host.
    # The measured defect did not return LATE with the right answer — it
    # returned the hung pane's `UNAVAILABLE` diagnostic as the trigger and
    # reported the already-finished gate as unfinished, so a serializing
    # adapter fails on the trigger identity, the outcome label and the exit
    # code, every run, whatever the host was doing.
    assert result.trigger_target == gate.identity
    assert result.command_outcome == "target-ended"
    assert result.trigger_exit_code == _FINISHED_GATE_EXIT_CODE
    assert pane.identity in result.unfinished_targets
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

    EVERY WAIT HERE RUNS ON AN INJECTED CLOCK, armed at a pinned instant. That
    is what turns the reported timestamp from "at or after some reading nobody
    controls" into the exact deadline the wait was given, and it is what makes
    the overshoot a decision rather than a hope — `_settling_sleeper` carries
    the reasoning, including why it must still let the probe's real read FINISH
    for the defective loop to have anything to mis-read.
    """
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "lone-hung.sock"
    endings: list[tuple[str, str | None, tuple[str, ...]]] = []
    stale_readings: list[tuple[str, bool, float]] = []

    with _hung_peer(socket_path=socket_path) as received:
        pane = _hung_pane(socket_path=socket_path, terminal_id="term_lone")
        for run in range(_LONE_RUNS):
            clock = _InjectedClock()
            watcher = _WatchingPaneLauncher()
            result = run_wait(
                request=WaitRequest(
                    wait_id=f"lone-hung-pane-{run}",
                    session_id="deadline-safety",
                    repository=tmp_path,
                    deadline_seconds=_LONE_DEADLINE_SECONDS,
                    targets=(pane,),
                    started_at=_PINNED_START,
                ),
                launcher=RoutingLauncher(
                    gate=GateStatusLauncher(repository=tmp_path),
                    pane=watcher,
                ),
                wait_store_root=wait_store_root,
                monotonic=clock.read,
                sleeper=_settling_sleeper(clock=clock, watcher=watcher),
            )
            observation = result.observations[pane.identity]
            endings.append(
                (result.command_outcome, result.trigger_target, result.unfinished_targets)
            )
            stale_readings.append((observation.state, observation.fresh, observation.observed_at))

    assert endings == [("deadline", None, (pane.identity,))] * _LONE_RUNS
    # What an unfinished target owes: `UNAVAILABLE` says this wait measured no
    # state at all, `fresh=False` says the reading is not a current one, and the
    # timestamp is the expiry the wait returned at — asserted as that EXACT
    # instant, which the pinned arming instant and the injected clock make
    # knowable rather than merely bounded.
    expiry = _PINNED_START + _LONE_DEADLINE_SECONDS
    assert stale_readings == [(DIAGNOSTIC_UNAVAILABLE, False, expiry)] * _LONE_RUNS
    # The hung target was READ and never written to, so the work that got
    # cancelled at expiry was this wait's own and nothing belonging to the pane.
    assert received, "the wait never reached the hung peer at all"
    for request in received:
        assert json.loads(request.decode("utf-8"))["method"] == "agent.get"


def test_a_lone_hung_pane_wait_is_ended_by_cancellation_not_by_its_own_timeout(
    *,
    tmp_path: Path,
) -> None:
    """Scenario 156: expiry CANCELS the hung probe; its own timeout never runs.

    The budget a hung observation's read blocks in used to BE the remaining
    deadline, so the probe's timeout and the wait's expiry fell on the same
    instant. That coincidence is what put the sibling assertion's outcome
    label up for grabs, and it also left `the wait returns without waiting for
    the probe's own socket timeout` with nothing to assert: there was no
    interval between the two to return inside of.

    The budget is therefore read off the wait's OWN probe and asserted to
    outlast the deadline — THAT comparison is the discriminator, and it is pure
    arithmetic on two declared numbers: a probe whose read budget still WAS the
    remaining deadline fails it on every host. The return landing inside that
    budget is then read off the INJECTED clock, which advances only by what the
    wait asked to sleep, so the reading is the budget that wait spent rather
    than a verdict on the scheduler. The worker's JOIN is the deterministic
    completion event proving cancellation released it before the test examines
    the cancelled task.
    """
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "budget-hung.sock"
    watcher = _WatchingPaneLauncher()
    clock = _InjectedClock()
    reached = threading.Event()

    with _hung_peer(socket_path=socket_path, on_receive=reached.set) as received:
        pane = _hung_pane(socket_path=socket_path, terminal_id="term_budget")
        result = run_wait(
            request=WaitRequest(
                wait_id="lone-hung-pane-budget",
                session_id="deadline-safety",
                repository=tmp_path,
                deadline_seconds=_LONE_DEADLINE_SECONDS,
                targets=(pane,),
                started_at=_PINNED_START,
            ),
            launcher=RoutingLauncher(
                gate=GateStatusLauncher(repository=tmp_path),
                pane=watcher,
            ),
            wait_store_root=wait_store_root,
            monotonic=clock.read,
            sleeper=_reaching_sleeper(clock=clock, reached=reached),
        )
        spent = clock.read() - _PINNED_START
        task = watcher.probes[0].tasks[0]
        assert task is not None
        read_budget = task.channel.timeout_seconds
        assert read_budget > _LONE_DEADLINE_SECONDS, (
            f"a {read_budget}s read budget cannot outlast a " f"{_LONE_DEADLINE_SECONDS}s deadline"
        )
        assert result.command_outcome == "deadline"
        assert spent < read_budget, f"the wait waited out its probe's budget in {spent}s"
        # The probe was CANCELLED, and its worker is GONE rather than merely
        # unreported: joining is the completion event that establishes it no
        # longer holds the socket.
        assert task.cancel_requested is True
        assert task.thread is not None
        task.thread.join()
        assert task.thread.is_alive() is False, "the hung observation outlived its cancellation"
        # A cancelled read measured nothing, so whatever it returned is not an
        # observation of the pane and is discarded rather than reported.
        assert task.result is None
        assert watcher.probes[0].inner.active is False

    assert received, "the wait never reached the hung peer at all"
    for request in received:
        assert json.loads(request.decode("utf-8"))["method"] == "agent.get"


def test_registration_lock_is_inside_the_original_deadline(*, tmp_path: Path) -> None:
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    result_outcomes: list[str] = []
    clock = _InjectedClock()

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
            monotonic=clock.read,
            sleeper=clock.sleep,
        )
        result_outcomes.append(result.command_outcome)

    lock_path = wait_store_root / ".inventory.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        worker = threading.Thread(target=invoke_wait)
        worker.start()
        # The worker advances its injected budget while this lock remains held,
        # then exits at that exact deadline. Joining it is the condition this
        # case needs; a host-time wait would only guess when that occurs.
        worker.join()
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert result_outcomes == ["deadline"]
    assert worker.is_alive() is False


def test_cancelling_gate_observer_leaves_gate_untouched(*, tmp_path: Path) -> None:
    run_dir = tmp_path / "gate-runs/live"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)
    probe = GateStatusLauncher(repository=tmp_path).launch(target=target, timeout_seconds=1.0)
    # Fixed observation instants. The gate adapter records whatever instant it
    # is handed and nothing here grades WHEN it was observed, so reading the
    # host clock for these would only make the recorded value unpredictable.
    assert probe.poll(now=_PINNED_START).state == "RUNNING"
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    probe.cancel(timeout_seconds=0.0)
    assert probe.active is False
    assert probe.poll(now=_PINNED_START + 1.0).state == "RUNNING"
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before
