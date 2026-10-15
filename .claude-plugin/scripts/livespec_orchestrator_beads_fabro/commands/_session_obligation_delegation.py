"""The boundary a coordinator's dispatched or delegated target actually goes through.

`_session_obligation_launch` owns the ORDERING a protected launch obeys and
`_session_obligation_reconcile` owns the crash repair; this module is the one
place the product puts a REAL target through both. Its two observers are the two
kinds `contracts.md` section "Launch obligations and consumed recovery" names
when it says the boundary "MUST attach the actual gate/run/delegation identity":
a detached gate run, which is how authorized work is DISPATCHED here, and a
Herdr pane, which is how a turn's work is DELEGATED to another session.

WHY THE OBSERVER IS THE EFFECT. The external effect at this boundary is the
coordinator's own — `just gate-start` started the gate, Herdr owns the pane —
so what the boundary performs is the ATTACHMENT: it asks the target's own store
for the identity that now exists and answers with it. That keeps the ordering
the clause requires (intent persisted, then the real identity attached, then and
only then a protected launch reported) without this surface ever becoming a
second way to start work, which is also why nothing here can kill anything.

WHY AN UNOBSERVABLE TARGET IS NOT AN ERROR. Freezing a gate or a pane RAISES
when the target cannot be identified, and that is right for the wait surface,
whose caller named a target it expects to block on. Here it is a STATE: the
obligation is already durable, so the honest outcome is `attachment-pending` —
an obligation recorded, not yet attached, and therefore not protected. Letting
the raise escape would discard the registration's whole point by reporting a
recorded obligation as a failed command.

WHY THE RETRY RECONCILES RATHER THAN RE-REGISTERING. Running this boundary twice
under one operation id means a previous attempt already reached the record, so
`protected_launch` refuses to launch again and hands the question on. That is
exactly the crash window the reconciliation exists for, and the ordinary retry
is the path it is reached by: the second call completes the ORIGINAL
obligation's attachment from a fresh observation — preserving its epoch,
deadline and authority — instead of opening a second obligation for one piece
of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    CoverageReading,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    DIAGNOSTIC_INTENT_ALREADY_RECORDED,
    LAUNCH_ATTACHMENT_PENDING,
    LAUNCH_PROTECTED,
    LaunchVerdict,
    protected_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_reconcile import (
    RECONCILE_ALREADY_ATTACHED,
    RECONCILE_ATTACHED,
    reconcile_launch_attachment,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    LaunchIntent,
    LaunchTarget,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import freeze_pane_target
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateTarget,
    WaitTarget,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "DelegationOutcome",
    "TargetObservation",
    "gate_launch_observer",
    "pane_launch_observer",
    "register_launch",
]

# The reconciliation states that leave the obligation genuinely attached. Both
# count as protection: the coverage grade was passed before the intent was ever
# written, so an attached obligation under a verified grade is exactly what a
# protected launch IS. They stay two values rather than one because only the
# first says THIS call performed the attachment.
_ATTACHED_RECONCILIATIONS = frozenset({RECONCILE_ATTACHED, RECONCILE_ALREADY_ATTACHED})


class TargetObservation(Protocol):
    """One read of the real target an operation launched."""

    def __call__(self, *, operation_id: str) -> LaunchTarget | None: ...


@dataclass(frozen=True, kw_only=True)
class DelegationOutcome:
    """What one registration established, and the repair it ran to get there.

    `reconciliation` is `None` on the ordinary first call and names the repair's
    own state on a retry, so an operator can tell a launch that registered
    cleanly from one whose attachment was completed after a crash. Reporting it
    is what keeps the second call from looking like the first.
    """

    state: str
    operation_id: str
    coverage_state: str
    diagnostic: str | None
    target: LaunchTarget | None
    reconciliation: str | None

    @property
    def protected(self) -> bool:
        return self.state == LAUNCH_PROTECTED

    def payload(self) -> dict[str, object]:
        return {
            "coverage_state": self.coverage_state,
            "diagnostic": self.diagnostic,
            "operation_id": self.operation_id,
            "protected": self.protected,
            "reconciliation": self.reconciliation,
            "state": self.state,
            "target": None if self.target is None else self.target.record_payload(),
        }


def _launch_target(*, frozen: WaitTarget) -> LaunchTarget:
    """One frozen wait target, as the obligation record's kind and identity.

    Both spellings are the target's OWN, read off the frozen value rather than
    composed here, so an obligation and a wait row name one target with one
    string and a reader can join them.
    """
    return LaunchTarget(kind=frozen.kind, identity=frozen.identity)


def gate_launch_observer(*, gate_store_root: Path, run_id: str) -> TargetObservation:
    """Observe the DISPATCHED target: one detached gate run, as it now stands."""

    def observe(*, operation_id: str) -> LaunchTarget | None:
        del operation_id
        frozen = attempt(
            action=lambda: GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id),
            exceptions=(OSError, UnicodeError),
        )
        return None if isinstance(frozen, AttemptFailure) else _launch_target(frozen=frozen)

    return observe


def pane_launch_observer(
    *, socket_path: Path, pane_id: str, timeout_seconds: float
) -> TargetObservation:
    """Observe the DELEGATED target: one Herdr pane, as its server now reports it."""

    def observe(*, operation_id: str) -> LaunchTarget | None:
        del operation_id
        frozen = attempt(
            action=lambda: freeze_pane_target(
                socket_path=socket_path, pane_id=pane_id, timeout_seconds=timeout_seconds
            ),
            exceptions=(OSError, UnicodeError, ValueError),
        )
        return None if isinstance(frozen, AttemptFailure) else _launch_target(frozen=frozen)

    return observe


@dataclass(frozen=True, kw_only=True)
class _ObservedEffectReader:
    """`LaunchedEffectReader` over the observation this registration already holds.

    The adapter exists because the two protocols differ only in their verb — a
    launch effect is CALLED and a reconciliation reader is ASKED — and one
    observation has to serve both, or the repair would read the target through
    an instrument the launch never used.
    """

    observation: TargetObservation

    def observe(self, *, operation_id: str) -> LaunchTarget | None:
        return self.observation(operation_id=operation_id)


def register_launch(
    *,
    intent: LaunchIntent,
    coverage: CoverageReading,
    obligation_store_root: Path,
    observe: TargetObservation,
    now: float,
) -> DelegationOutcome:
    """Register one launch obligation and attach the real target it names."""
    verdict = protected_launch(
        intent=intent,
        coverage=coverage,
        obligation_store_root=obligation_store_root,
        effect=observe,
        now=now,
    )
    if verdict.diagnostic != DIAGNOSTIC_INTENT_ALREADY_RECORDED:
        return _outcome(verdict=verdict, reconciliation=None)
    return _reconciled(
        verdict=verdict,
        obligation_store_root=obligation_store_root,
        observe=observe,
        now=now,
    )


def _reconciled(
    *,
    verdict: LaunchVerdict,
    obligation_store_root: Path,
    observe: TargetObservation,
    now: float,
) -> DelegationOutcome:
    """Complete the ORIGINAL obligation's attachment, idempotently, on a retry."""
    outcome = reconcile_launch_attachment(
        obligation_store_root=obligation_store_root,
        operation_id=verdict.operation_id,
        reader=_ObservedEffectReader(observation=observe),
        observed_at=now,
    )
    attached = outcome.state in _ATTACHED_RECONCILIATIONS
    return DelegationOutcome(
        state=LAUNCH_PROTECTED if attached else LAUNCH_ATTACHMENT_PENDING,
        operation_id=verdict.operation_id,
        coverage_state=verdict.coverage_state,
        diagnostic=None if attached else verdict.diagnostic,
        target=outcome.target if attached else None,
        reconciliation=outcome.state,
    )


def _outcome(*, verdict: LaunchVerdict, reconciliation: str | None) -> DelegationOutcome:
    return DelegationOutcome(
        state=verdict.state,
        operation_id=verdict.operation_id,
        coverage_state=verdict.coverage_state,
        diagnostic=verdict.diagnostic,
        target=verdict.target,
        reconciliation=reconciliation,
    )
