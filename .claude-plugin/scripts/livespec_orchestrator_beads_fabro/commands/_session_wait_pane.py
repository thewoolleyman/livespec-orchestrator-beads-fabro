"""Herdr pane wait targets observed through the bounded socket API."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_herdr import (
    DIAGNOSTIC_UNAVAILABLE,
    HerdrChannel,
    HerdrReply,
    herdr_socket_generation,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    PaneTarget,
)

__all__: list[str] = [
    "DIAGNOSTIC_GONE",
    "DIAGNOSTIC_REPLACED",
    "HERDR_BACKEND",
    "HerdrPaneLauncher",
    "HerdrPaneProbe",
    "freeze_pane_target",
    "observe_pane_target",
    "pane_observation",
]

HERDR_BACKEND = "herdr"

# The two ends that are about the TARGET'S IDENTITY rather than about one
# reply: its server is no longer there at all, or the thing answering is not
# the instance that was armed. They reuse the gate adapter's own vocabulary so
# one operator reads both target kinds the same way.
DIAGNOSTIC_GONE = "GONE"
DIAGNOSTIC_REPLACED = "REPLACED"

_DEFAULT_TIMEOUT_SECONDS = 5.0

# How far a probe's own read budget OUTLASTS the deadline budget the wait hands
# it. The budget bounds a read that cancellation is expected to interrupt, so
# it is a BACKSTOP rather than the wait's bound — and a backstop that expires
# at the same instant the bound does is not one. A budget equal to the
# remaining deadline made a hung probe's timeout diagnostic arrive together
# with the deadline, and a diagnostic is not a running state, so whichever the
# final poll round saw first decided the outcome label: measured 2026-10-13,
# two consecutive runs of one three-second wait whose only target was a pane
# that never answers returned `target-ended` and then `deadline` for the
# identical request. One second is longer than the wait's own one-second poll
# cadence, so the round that observes expiry cannot also be the round that
# observes the timeout — and it leaves a real interval for the wait to return
# inside of rather than a coincidence nothing can assert against.
_READ_BUDGET_GRACE_SECONDS = 1.0


def _reported_terminal_id(*, reply: HerdrReply) -> str | None:
    """The pane's own terminal identity, or None when the reply carries none.

    This is the PROCESS generation half of a pane's identity: Herdr mints a
    fresh terminal id per pane, so a pane id reused by a later terminal — on
    this server or on a restarted one — carries a different value and is
    therefore observable as a replacement rather than as the armed pane.
    """
    agent = reply.agent
    if agent is None:
        return None
    terminal_id = agent.get("terminal_id")
    return terminal_id if isinstance(terminal_id, str) else None


def freeze_pane_target(
    *,
    socket_path: Path,
    pane_id: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> PaneTarget:
    """Bind one live Herdr pane's full identity before a wait may block.

    The identity is frozen from what the server reports NOW, so a pane this
    server cannot identify is refused HERE rather than armed and then reported
    as a diagnostic for the rest of the wait. The raise is bug-class on
    purpose: the caller named a pane that does not exist, which is a
    precondition failure of the request and not a state of any target.
    """
    generation = herdr_socket_generation(socket_path=socket_path)
    if generation is None:
        absent = f"no {HERDR_BACKEND} server socket at {socket_path}"
        raise FileNotFoundError(absent)
    reply = HerdrChannel(
        socket_path=socket_path,
        timeout_seconds=timeout_seconds,
    ).agent_info(pane_id=pane_id)
    terminal_id = _reported_terminal_id(reply=reply)
    if terminal_id is None:
        where = f"{HERDR_BACKEND} pane {pane_id} at {socket_path}"
        unidentifiable = f"{where} is not identifiable ({reply.diagnostic})"
        raise ValueError(unidentifiable)
    return PaneTarget(
        backend=HERDR_BACKEND,
        socket_path=socket_path,
        server_generation=generation,
        pane_id=pane_id,
        terminal_id=terminal_id,
    )


def _server_diagnostic(*, target: PaneTarget) -> str | None:
    """Whether this target's SERVER is still the one that was armed.

    Asked BEFORE the pane is, and that order is load-bearing: a restarted
    server at the same socket path mints pane ids from the same sequence, so
    the frozen pane id routinely resolves on the new instance. Asking the pane
    first would get a clean, plausible state back from a server nobody armed
    against.
    """
    generation = herdr_socket_generation(socket_path=target.socket_path)
    if generation is None:
        return DIAGNOSTIC_GONE
    if generation != target.server_generation:
        return DIAGNOSTIC_REPLACED
    return None


def _diagnostic(*, target: PaneTarget, state: str, observed_at: float) -> GateObservation:
    return GateObservation(
        target=target,
        state=state,
        exit_code=None,
        observed_at=observed_at,
        fresh=True,
    )


def pane_observation(
    *,
    target: PaneTarget,
    observed_at: float,
    channel: HerdrChannel,
) -> GateObservation:
    """This frozen pane's state now, or why it could not be read.

    The state is reported as the backend's OWN vocabulary rather than mapped
    onto the gate vocabulary: `done`, `blocked`, `idle` and `unknown` are
    different outcomes to an operator and collapsing them would turn a pane
    that is waiting on a human into one that finished its work.
    """
    server = _server_diagnostic(target=target)
    if server is not None:
        return _diagnostic(target=target, state=server, observed_at=observed_at)
    reply = channel.agent_info(pane_id=target.pane_id)
    agent = reply.agent
    if agent is None:
        return _diagnostic(
            target=target,
            state=str(reply.diagnostic),
            observed_at=observed_at,
        )
    if _reported_terminal_id(reply=reply) != target.terminal_id:
        # The pane id resolves, but to a DIFFERENT terminal than the one that
        # was armed. Reporting its state would answer a question about
        # somebody else's pane, which is exactly the retargeting this frozen
        # identity exists to refuse.
        return _diagnostic(target=target, state=DIAGNOSTIC_REPLACED, observed_at=observed_at)
    status = agent.get("agent_status")
    if not isinstance(status, str):
        return _diagnostic(
            target=target,
            state=DIAGNOSTIC_UNAVAILABLE,
            observed_at=observed_at,
        )
    return GateObservation(
        target=target,
        state=status,
        exit_code=None,
        observed_at=observed_at,
        fresh=True,
    )


def observe_pane_target(*, target: PaneTarget, observed_at: float) -> GateObservation:
    """One fresh observation of a pane target, on its own bounded channel."""
    return pane_observation(
        target=target,
        observed_at=observed_at,
        channel=HerdrChannel(
            socket_path=target.socket_path,
            timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        ),
    )


@dataclass(kw_only=True)
class _PaneTask:
    """One pane observation running off the caller's own thread."""

    target: PaneTarget
    observed_at: float
    channel: HerdrChannel
    result: GateObservation | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)
    ready: threading.Event = field(default_factory=threading.Event, init=False)
    cancel_requested: bool = field(default=False, init=False)

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.ready.set()
        if self.cancel_requested:
            # Cancellation landed before this worker reached its observation,
            # so no socket is opened at all. This is what makes `cancel` SOUND
            # rather than fail-open when it wins that race: without it an
            # unready task would go on to open a connection after cancellation
            # had already reported itself clean.
            return
        observation = pane_observation(
            target=self.target,
            observed_at=self.observed_at,
            channel=self.channel,
        )
        if not self.cancel_requested:
            self.result = observation

    def poll(self) -> GateObservation | None:
        return self.result

    def cancel(self, *, timeout_seconds: float) -> None:
        """Stop this observation's work, touching nothing on the server.

        NEVER raises on a lost race. `run_wait` cancels on every return path,
        the successful first-event one included, so an exception here would
        discard a bounded result that had already been computed and report the
        whole wait as a crash.

        The SOCKET is interrupted before the join, and that order is
        load-bearing: a worker blocked in `recv` holds its budget, which for a
        probe OUTLASTS the whole remaining deadline, so joining first would
        make cancellation cost more than the delay it exists to avoid.
        """
        started = time.monotonic()
        self.cancel_requested = True
        self.channel.cancel()
        _ = self.ready.wait(timeout=timeout_seconds)
        thread = self.thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout_seconds - (time.monotonic() - started)))


@dataclass(kw_only=True)
class HerdrPaneProbe:
    target: PaneTarget
    timeout_seconds: float
    task: _PaneTask | None = field(default=None, init=False)

    @property
    def active(self) -> bool:
        return self.task is not None

    def poll(self, *, now: float) -> GateObservation | None:
        """This pane's observation once it has landed, else None.

        The observation runs on its OWN worker rather than on the polling
        thread, and that is what keeps one pane from serializing an entire
        wait. A peer that accepts and never answers holds its socket for this
        probe's whole read budget, which outlasts the remaining deadline, so a
        synchronous poll spends that whole budget before any sibling target is
        looked at even once — measured against the synchronous adapter, a wait
        over a hung pane and an ALREADY-FINISHED gate returned the hung pane's
        diagnostic at 20.02s of a 20s deadline and reported the finished gate
        as unfinished. Answering None while the work is in flight is what
        leaves the caller free to poll its other targets at its own cadence.

        A fresh channel per task is deliberate: a cancelled channel stays
        cancelled, so reusing one would refuse every later observation.
        """
        if self.task is None:
            self.task = _PaneTask(
                target=self.target,
                observed_at=now,
                channel=HerdrChannel(
                    socket_path=self.target.socket_path,
                    timeout_seconds=self.timeout_seconds + _READ_BUDGET_GRACE_SECONDS,
                ),
            )
            self.task.start()
        observation = self.task.poll()
        if observation is None:
            return None
        self.task = None
        return observation

    def cancel(self, *, timeout_seconds: float) -> None:
        """Stop any in-flight observation. Nothing on the server is touched."""
        if self.task is not None:
            self.task.cancel(timeout_seconds=timeout_seconds)
        self.task = None


@dataclass(frozen=True, kw_only=True)
class HerdrPaneLauncher:
    def launch(self, *, target: PaneTarget, timeout_seconds: float) -> HerdrPaneProbe:
        return HerdrPaneProbe(target=target, timeout_seconds=timeout_seconds)
