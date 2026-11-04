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
# A FAILURE bound on joining a pane worker whose read budget has been allowed to
# run out, never a timing assertion: the join's RETURN is the deterministic
# event the settling sleeper waits on.
_WORKER_SETTLE_SECONDS = 30.0
# The instant the wait below is armed at, supplied through `WaitRequest` so the
# deadline is an exact number this module can assert against.
_PINNED_START = 0.0
# Repeated runs of ONE request, because the defect was an unstable label
# rather than a wrong one: the same wait reported `target-ended` and then
# `deadline` on two consecutive runs.
_LONE_RUNS = 2
# A hang guard only: every wait bounded by it ends on its own event long before.
_HANG_GUARD_SECONDS = 30.0
# Far longer than any wait here, so a probe read still pending when the wait
# cancels it cannot have been released by its own budget instead.
_LONG_READ_BUDGET_SECONDS = 300.0


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
    """The monotonic clock a wait reads, advanced only by the sleeper beside it."""

    now: float = _PINNED_START

    def read(self) -> float:
        return self.now

    def sleep(self, *, seconds: float) -> None:
        self.now += seconds


def _settling_sleeper(
    *, clock: _InjectedClock, watcher: _WatchingPaneLauncher
) -> Callable[..., None]:
    """Let every in-flight pane read FINISH, then advance the clock past expiry.

    The measured race turned on whether the round that observes expiry ALSO sees
    the hung probe's timeout diagnostic. Two things must hold when that round
    runs, and each has its own mechanism: the probe's worker has EXITED (the
    sleeper joins it, an event rather than an interval), so a diagnostic exists
    for a defective loop to mis-read as a finished target; and the deadline has
    PASSED (arithmetic on the injected clock).
    """

    def sleeper(*, seconds: float) -> None:
        for probe in watcher.probes:
            task = probe.inner.task
            assert task is not None, "the probe started no observation"
            assert task.thread is not None, "the observation started no worker"
            task.thread.join(timeout=_WORKER_SETTLE_SECONDS)
        clock.sleep(seconds=seconds + _POLL_OVERSHOOT_SECONDS)

    return sleeper


@dataclass(kw_only=True)
class _DeadlineAfterPaneReadClock:
    """A wait clock that reaches expiry only after its pane read is in flight.

    Registration and launcher work may take longer than a short wait budget on
    a loaded host. Holding this clock at zero makes that scheduling irrelevant:
    the first poll starts the real pane worker, and the sleeper advances to the
    deadline only after the controlled peer has received its request. That
    receipt proves the worker reached the socket read this wait cancels.
    """

    read_started: threading.Event
    deadline: float
    now: float = 0.0
    read_started_before_deadline: bool = field(default=False, init=False)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, *, seconds: float) -> None:
        assert self.read_started.wait(
            timeout=_HANG_GUARD_SECONDS
        ), "the pane read did not start inside the hang guard"
        self.read_started_before_deadline = self.now < self.deadline
        self.now += seconds


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
    # Whether each cancellation found its observation's read still PENDING —
    # worker alive, nothing landed. That is the ordering every bound below
    # rests on: a wait that waited out a probe's budget would find the read
    # already over.
    pending_at_cancel: list[bool] = field(default_factory=list)

    def poll(self, *, now: float) -> GateObservation | None:
        observation = self.inner.poll(now=now)
        self.tasks.append(self.inner.task)
        return observation

    def cancel(self, *, timeout_seconds: float) -> None:
        task = self.inner.task
        self.pending_at_cancel.append(
            task is not None
            and task.thread is not None
            and task.thread.is_alive()
            and task.result is None
        )
        self.inner.cancel(timeout_seconds=timeout_seconds)


@dataclass(kw_only=True)
class _WatchingPaneLauncher:
    """The real pane launcher, keeping every probe it hands a wait.

    `read_budget_seconds`, when set, replaces the budget the wait asks for, so a
    case can give a hung read a budget no wait in this module lasts. It is a
    floor: a wait asking for more still gets what it asked for.
    """

    probes: list[_WatchedPaneProbe] = field(default_factory=list)
    read_budget_seconds: float = 0.0

    def launch(self, *, target: PaneTarget, timeout_seconds: float) -> _WatchedPaneProbe:
        budget = max(timeout_seconds, self.read_budget_seconds)
        probe = _WatchedPaneProbe(
            inner=HerdrPaneLauncher().launch(target=target, timeout_seconds=budget),
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
        watcher = _WatchingPaneLauncher()
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
                pane=watcher,
            ),
            wait_store_root=wait_store_root,
        )

    # The finished gate is what woke the wait, carrying its OWN exit code.
    assert result.trigger_target == gate.identity
    assert result.command_outcome == "target-ended"
    assert result.trigger_exit_code == _FINISHED_GATE_EXIT_CODE
    assert pane.identity in result.unfinished_targets
    # Returned while the hung pane's read was still PENDING. A wait that polled
    # the hung pane on its own thread could only return once that probe's
    # budget expired, which is the entire deadline, and would find the read
    # already over. An ordering, so a loaded host cannot flip it.
    assert watcher.probes[0].pending_at_cancel[:1] == [True]
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
    # state at all, `fresh=False` says the reading is not a current one, and
    # the timestamp is the expiry the wait returned at, asserted as that EXACT
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

    The probe's read is given a budget far longer than this case's own
    patience, the way the cancel-race cases do, and the budget is read off the
    wait's OWN probe and asserted to outlast the deadline. The cancellation is
    then asserted to find that read still pending, and the worker to exit
    inside a hang guard that is a small fraction of the budget. Both are
    orderings rather than stopwatch readings, which is what tells a worker
    released by the cancellation apart from one released by the timeout it was
    supposed to pre-empt on a loaded host as well as an idle one.
    """
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    socket_path = tmp_path / "budget-hung.sock"
    watcher = _WatchingPaneLauncher(read_budget_seconds=_LONG_READ_BUDGET_SECONDS)
    read_started = threading.Event()
    clock = _DeadlineAfterPaneReadClock(
        read_started=read_started,
        deadline=_LONE_DEADLINE_SECONDS,
    )

    with _hung_peer(socket_path=socket_path, on_receive=read_started.set) as received:
        pane = _hung_pane(socket_path=socket_path, terminal_id="term_budget")
        result = run_wait(
            request=WaitRequest(
                wait_id="lone-hung-pane-budget",
                session_id="deadline-safety",
                repository=tmp_path,
                deadline_seconds=_LONE_DEADLINE_SECONDS,
                targets=(pane,),
            ),
            launcher=RoutingLauncher(
                gate=GateStatusLauncher(repository=tmp_path),
                pane=watcher,
            ),
            wait_store_root=wait_store_root,
            monotonic=clock.monotonic,
            sleeper=clock.sleep,
        )
        assert clock.read_started_before_deadline is True
        task = watcher.probes[0].tasks[0]
        assert task is not None
        read_budget = task.channel.timeout_seconds
        assert read_budget > _LONE_DEADLINE_SECONDS, (
            f"a {read_budget}s read budget cannot outlast a " f"{_LONE_DEADLINE_SECONDS}s deadline"
        )
        assert result.command_outcome == "deadline"
        # The wait cancelled the read while it was still PENDING, so it did not
        # wait out the probe's budget: a read that had run to its own timeout
        # would already be over.
        assert watcher.probes[0].pending_at_cancel == [True]
        # The probe was CANCELLED, and its worker is GONE rather than merely
        # unreported: a thread that has exited cannot still be holding the
        # socket, and a thread cannot exit inside this hang guard on a budget
        # ten times longer than it.
        assert task.cancel_requested is True
        assert task.thread is not None
        task.thread.join(timeout=_HANG_GUARD_SECONDS)
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
        # Waited on WHILE the lock is still held: a registration that queued
        # behind the lock rather than honouring the deadline could only return
        # after the unlock below, so the ordering is the bound. The timeout is
        # a hang guard, never the verdict.
        returned_by_bound = returned.wait(timeout=_HANG_GUARD_SECONDS)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    worker.join(timeout=_HANG_GUARD_SECONDS)

    assert returned_by_bound is True
    assert result_outcomes == ["deadline"]
    assert worker.is_alive() is False


def test_cancelling_gate_observer_leaves_gate_untouched(*, tmp_path: Path) -> None:
    run_dir = tmp_path / "gate-runs/live"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)
    probe = GateStatusLauncher(repository=tmp_path).launch(target=target, timeout_seconds=1.0)
    # Fixed observation instants: the gate adapter records whatever instant it
    # is handed and nothing here grades WHEN it was observed.
    assert probe.poll(now=_PINNED_START).state == "RUNNING"
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    probe.cancel(timeout_seconds=0.0)
    assert probe.active is False
    assert probe.poll(now=_PINNED_START + 1.0).state == "RUNNING"
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before
