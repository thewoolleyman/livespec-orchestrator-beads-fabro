"""Cancelling a Herdr pane observation must not pin, raise, or touch the pane.

Scenario 156 of `SPECIFICATION/scenarios.md` governs this module. The
behavioural proof that an already-finished sibling returns first lives in
`test_session_wait_deadline_safety`; these cases pin the cancellation races
underneath it, which that proof reaches but cannot distinguish.

Two properties are at stake and they pull in opposite directions. `run_wait`
cancels every probe on EVERY return path, the successful first-event one
included, so a cancel that RAISES discards a bounded result that had already
been computed and reports the whole wait as a crash. But a cancel that merely
stops waiting leaves its worker blocked in `recv` holding the entire remaining
deadline — which is the cost the asynchronous probe exists to avoid, so
"did not raise" is not on its own evidence of cancellation.

Every peer here is a CONTROLLED PEER — a local unix socket this test binds and
owns — because no healthy Herdr server can be asked to accept a connection and
then never answer. Nothing here touches a pane, workspace or server it did not
create, and no peer is ever sent a mutating call.
"""

from __future__ import annotations

import select
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_herdr import (
    DIAGNOSTIC_UNAVAILABLE,
    HerdrChannel,
    herdr_socket_generation,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import (
    HerdrPaneLauncher,
    _PaneTask,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import PaneTarget

# Far longer than any assertion below waits. The budget is the thing under
# test: a cancellation that returned only when the read's own budget expired
# would be indistinguishable from one that interrupted it if the budget were
# short, so it is deliberately longer than the test's own patience.
_LONG_BUDGET_SECONDS = 300.0
# A FAILURE bound on joining a worker that has already been asked to finish,
# never a timing assertion: the join's own return is the event each case waits
# on, and the `is_alive` check after it is what reports a worker that did not.
_JOIN_SECONDS = 30.0


def _pane_target(*, socket_path: Path) -> PaneTarget:
    """A target whose SERVER identity matches, so the hang is in the channel.

    The generation is read from the peer's own socket file. A mismatched one
    would be answered by the identity arm before any connection was attempted,
    which is a different end entirely and would make every case below pass
    without exercising the transport at all.
    """
    return PaneTarget(
        backend="herdr",
        socket_path=socket_path,
        server_generation=str(herdr_socket_generation(socket_path=socket_path)),
        pane_id="w1:p1",
        terminal_id="term_cancel",
    )


@dataclass(kw_only=True)
class _Peer:
    """What one controlled peer saw, as a connection log plus a wakeup.

    Both are needed and neither replaces the other. `connections` answers "did
    the adapter open one at all", which is what tells `cancelled before it ever
    ran` apart from `ran and was interrupted` — two states that produce the
    same result object and the same absence of a reply. `connected` lets a test
    BLOCK until a read is genuinely in flight instead of polling for it, so an
    assertion about interrupting a read cannot be measured before one exists.

    `listener` is what makes the ABSENCE assertions sound without a settle. A
    unix `connect` completes against the kernel's listen BACKLOG whether or not
    this peer's accept loop has reached it, so a stray connection lands there
    first and `connections` can still be empty when a test looks. Reading the
    backlog directly, with a zero timeout, reports it immediately — so a caller
    joins every thread that could have connected and then ASKS, rather than
    sleeping for a quarter of a second and hoping that was long enough.
    """

    listener: socket.socket
    connections: list[socket.socket] = field(default_factory=list)
    connected: threading.Event = field(default_factory=threading.Event)

    def opened_a_connection(self) -> bool:
        """Whether anything connected — accepted, or still in the backlog."""
        readable, _, _ = select.select([self.listener], [], [], 0)
        return bool(self.connections) or bool(readable)


@contextmanager
def _silent_peer(*, socket_path: Path) -> Iterator[_Peer]:
    """A socket that accepts, never answers, and records what reached it.

    Each accepted connection is held OPEN deliberately: closing it would end a
    probe's read with an empty buffer, and an empty buffer is a reply the probe
    can read, so the peer would no longer be hanging.
    """
    stop = threading.Event()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.settimeout(0.05)
    peer = _Peer(listener=listener)

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            peer.connections.append(connection)
            peer.connected.set()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield peer
    finally:
        stop.set()
        worker.join(timeout=30.0)
        for connection in peer.connections:
            connection.close()
        listener.close()


def test_cancelling_a_hung_observation_releases_its_worker(*, tmp_path: Path) -> None:
    """A cancelled probe INTERRUPTS its read rather than waiting it out.

    The worker is confirmed to be past `connect` before cancellation, so what
    is cancelled is a read genuinely in flight. The worker thread itself is the
    assertion: a thread that has exited cannot still be holding the socket, and
    unlike a wall-clock bound it cannot pass for the wrong reason on a fast
    machine.

    That reasoning used to sit beside a wall-clock bound anyway — `cancel`
    returning inside a tenth of `_LONG_BUDGET_SECONDS` — which has been
    removed. It measured the host rather than the cancellation, and the
    sentence above already says why it could add nothing: `cancel` JOINS the
    worker, so a thread that has exited by the time `cancel` returns is the
    same fact, established without a verdict on the scheduler.
    """
    socket_path = tmp_path / "hung.sock"
    with _silent_peer(socket_path=socket_path) as peer:
        probe = HerdrPaneLauncher().launch(
            target=_pane_target(socket_path=socket_path),
            timeout_seconds=_LONG_BUDGET_SECONDS,
        )
        # The observation is in flight, so the first poll has no answer yet.
        assert probe.poll(now=1.0) is None
        assert probe.active is True
        task = probe.task
        assert task is not None
        assert peer.connected.wait(timeout=_JOIN_SECONDS) is True, "the probe never connected"
        # THE POSITIVE CONTROL for the absence assertions in the two cases
        # below. They report "nothing connected"; this is the same instrument
        # on a connection that genuinely happened, so an instrument that could
        # never return a hit fails here instead of certifying them.
        assert peer.opened_a_connection() is True

        probe.cancel(timeout_seconds=30.0)

    assert task.thread is not None
    assert task.thread.is_alive() is False, "the worker outlived its cancellation"
    assert probe.active is False
    # A cancelled observation is DISCARDED rather than reported: the read was
    # interrupted, so whatever it returned is not an observation of the pane.
    assert task.result is None


def test_a_pane_task_cancelled_before_it_runs_opens_no_connection(*, tmp_path: Path) -> None:
    """Skipping a socket for an unready task is only sound if none was opened.

    This is the race the `_cancelled` flag exists for. A cancellation landing
    before the worker reaches its observation must stop it from connecting at
    all, or cancellation would report itself clean while a fresh read was
    opened behind it.
    """
    socket_path = tmp_path / "unreached.sock"
    with _silent_peer(socket_path=socket_path) as peer:
        task = _PaneTask(
            target=_pane_target(socket_path=socket_path),
            observed_at=1.0,
            channel=HerdrChannel(
                socket_path=socket_path,
                timeout_seconds=_LONG_BUDGET_SECONDS,
            ),
        )
        task.cancel_requested = True

        task.start()
        assert task.thread is not None
        task.thread.join(timeout=_JOIN_SECONDS)

        # The JOIN is what makes the absence below sound: the only thread that
        # could have connected has exited, so no later connection is possible.
        # The backlog is read as well as the accepted list, because a connect
        # the accept loop has not reached yet lands there and nowhere else.
        assert task.thread.is_alive() is False
        assert peer.opened_a_connection() is False, "a cancelled task still connected"
    assert task.result is None


def test_cancelling_before_anything_is_in_flight_does_not_raise(*, tmp_path: Path) -> None:
    """Every way there is nothing to interrupt is an outcome, not a fault.

    A channel that never sent a request holds no socket, a task that was never
    started holds no thread, and a probe that was never polled holds no task.
    Each is the ordinary shape of a wait returning on a sibling's event, and
    each used to be one `None` away from raising.

    Each call is made DIRECTLY rather than through a raised-or-not helper: an
    exception is already a test failure carrying its own traceback, and
    wrapping one only buys a branch no passing run can ever take.
    """
    socket_path = tmp_path / "idle.sock"
    channel = HerdrChannel(socket_path=socket_path, timeout_seconds=1.0)
    channel.cancel()

    task = _PaneTask(
        target=_pane_target(socket_path=socket_path),
        observed_at=1.0,
        channel=HerdrChannel(socket_path=socket_path, timeout_seconds=1.0),
    )
    assert task.thread is None
    # A zero budget is what `run_wait` passes at expiry, which is exactly when
    # a task can still be holding no thread.
    task.cancel(timeout_seconds=0.0)
    assert task.result is None

    probe = HerdrPaneLauncher().launch(
        target=_pane_target(socket_path=socket_path),
        timeout_seconds=1.0,
    )
    assert probe.active is False
    probe.cancel(timeout_seconds=0.0)
    assert probe.active is False


def test_a_cancelled_channel_reports_unavailable_without_reaching_the_server(
    *,
    tmp_path: Path,
) -> None:
    """A cancelled channel measures nothing, and says so as a diagnostic.

    `UNAVAILABLE` rather than any pane state, for the same reason an
    unreachable server reports it: no state was read, and naming one would be
    a claim about the pane that nobody measured. The peer is asserted to have
    received NOTHING, which is what distinguishes a refused exchange from one
    that connected and was cut short.
    """
    socket_path = tmp_path / "never-reached.sock"
    with _silent_peer(socket_path=socket_path) as peer:
        channel = HerdrChannel(
            socket_path=socket_path,
            timeout_seconds=_LONG_BUDGET_SECONDS,
        )
        channel.cancel()

        # `agent_info` is synchronous on THIS thread, so by the time it has
        # returned every connection it was ever going to open has been opened.
        # Nothing is in flight behind it, which is why no settle is needed.
        reply = channel.agent_info(pane_id="w1:p1")

        assert peer.opened_a_connection() is False, "a cancelled channel still connected"
    assert reply.agent is None
    assert reply.diagnostic == DIAGNOSTIC_UNAVAILABLE
