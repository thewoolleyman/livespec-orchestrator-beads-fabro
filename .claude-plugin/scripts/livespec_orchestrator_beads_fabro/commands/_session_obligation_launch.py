"""The two boundaries that may report protection: a launch, and a turn's completion.

`contracts.md` section "Launch obligations and consumed recovery" fixes both.
For the launch: "Dispatch/delegation MUST persist intent, session/repository/
authorization scope, canonical result/epoch/original deadline and independently
verifiable wake/consumer coverage BEFORE reporting a protected launch." For the
completion: "Supported completion gates MUST verify durable launch obligations
and independent producer/consumer registration, preserving any existing
stricter supervised Stop rules." And for both: "A missing/unsupported
independent recovery owner MUST produce an explicit unmonitored refusal/
finding, never a claim of protected launch or completion."

WHY COVERAGE IS GRADED BEFORE ANYTHING ELSE HAPPENS. An uncovered launch is one
this boundary must not perform, so the grade has to precede the effect rather
than annotate it: grading afterwards would leave an external effect running
under an obligation nobody is watching, which is the exact incident this plan
exists to retire. The refusal therefore writes no record and calls no effect,
and `effect.calls == []` is the assertion that proves it.

WHY THE INTENT IS WRITTEN BEFORE THE EFFECT AND THE ORDER IS NOT NEGOTIABLE.
The record is what a crash leaves behind. Written after the effect, a crash in
between leaves a live target with no obligation — undiscoverable, because
nothing names it — whereas written before, the crash leaves an obligation with
no attachment, which `_session_obligation_reconcile` repairs from the stable
operation id. The expensive direction is losing the target, so the cheap record
goes first.

WHY AN ALREADY-RECORDED INTENT DOES NOT LAUNCH. Reaching this boundary twice
under one operation id means a previous attempt already got as far as the
record, so its effect may exist. Launching again would duplicate it, which the
same section forbids; so the second call reports `attachment-pending` and hands
the question to reconciliation, which is the surface that can ask the effect's
own store what happened.

WHY `protected` IS A PROPERTY RATHER THAN A FLAG A CALLER SETS. Every state
except one is a refusal or an unfinished launch, and a boolean field would let
a caller construct a verdict that claimed protection its own state contradicts.

WHY COMPLETION REPORTS THE OUTSTANDING IDS EVEN WHEN IT REFUSES. The refusal is
the finding, and a finding that named no work would leave an operator with
nothing to act on; the clause asks the completion gate to verify the durable
obligations, so naming them is part of the verdict rather than a nicety. It
reports them from the CENSUS, which reads the obligation store itself, so a
coordinator that never armed a wait still has its work enumerated — "An actual
owning session leaving its turn with unresolved authorized work MUST remain
covered even if it never arms a wait."

WHY AN UNREADABLE OBLIGATION STORE REFUSES COMPLETION AS UNOBSERVABLE. The
natural coding of an unlistable store is an empty census, and an empty census
reads as a session with nothing outstanding — the one reading that would let a
turn end cleanly while its work was invisible. So any census diagnostic refuses,
per "Missing/unreadable authority MUST be unobservable, not no obligations".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNOBSERVABLE,
    CoverageReading,
    CoverageVerdict,
    coverage_verdict,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    ATTACH_ALREADY_ATTACHED,
    ATTACH_ATTACHED,
    INTENT_RECORDED,
    LaunchIntent,
    LaunchTarget,
    attach_launch_target,
    outstanding_obligations,
    record_launch_intent,
)

__all__: list[str] = [
    "COMPLETION_PROTECTED",
    "COMPLETION_UNMONITORED",
    "COMPLETION_UNOBSERVABLE",
    "LAUNCH_ATTACHMENT_PENDING",
    "LAUNCH_PROTECTED",
    "LAUNCH_REGISTRATION_UNAVAILABLE",
    "LAUNCH_UNMONITORED",
    "LAUNCH_UNOBSERVABLE",
    "CompletionVerdict",
    "LaunchEffect",
    "LaunchVerdict",
    "protected_completion",
    "protected_launch",
]

LAUNCH_PROTECTED = "protected"
LAUNCH_UNMONITORED = "unmonitored"
LAUNCH_UNOBSERVABLE = "unobservable"
LAUNCH_REGISTRATION_UNAVAILABLE = "registration-unavailable"
LAUNCH_ATTACHMENT_PENDING = "attachment-pending"

COMPLETION_PROTECTED = "protected"
COMPLETION_UNMONITORED = "unmonitored"
COMPLETION_UNOBSERVABLE = "unobservable"

DIAGNOSTIC_INTENT_ALREADY_RECORDED = "intent-already-recorded"
DIAGNOSTIC_INTENT_UNAVAILABLE = "intent-unavailable"
DIAGNOSTIC_TARGET_UNOBSERVED = "launch-target-unobserved"
DIAGNOSTIC_ATTACHMENT_UNAVAILABLE = "attachment-unavailable"


class LaunchEffect(Protocol):
    """The external effect this boundary protects: a dispatch, or a delegation.

    It answers with the identity it created, which is what the boundary
    attaches. An effect that launched but cannot say what it launched answers
    `None`, and the obligation then waits for reconciliation rather than being
    reported as protected.
    """

    def __call__(self, *, operation_id: str) -> LaunchTarget | None: ...


@dataclass(frozen=True, kw_only=True)
class LaunchVerdict:
    state: str
    operation_id: str
    coverage_state: str
    diagnostic: str | None
    target: LaunchTarget | None

    @property
    def protected(self) -> bool:
        return self.state == LAUNCH_PROTECTED


@dataclass(frozen=True, kw_only=True)
class CompletionVerdict:
    state: str
    coverage_state: str
    diagnostic: str | None
    outstanding_operation_ids: tuple[str, ...]

    @property
    def protected(self) -> bool:
        return self.state == COMPLETION_PROTECTED


def protected_launch(
    *,
    intent: LaunchIntent,
    coverage: CoverageReading,
    obligation_store_root: Path,
    effect: LaunchEffect,
    now: float,
) -> LaunchVerdict:
    """Record the obligation, perform the effect, attach what it produced."""
    graded = coverage_verdict(reading=coverage)
    if not graded.verified:
        return _refused_launch(intent=intent, graded=graded)
    status = record_launch_intent(
        intent=intent,
        coverage=graded.record_payload(),
        obligation_store_root=obligation_store_root,
        recorded_at=now,
    )
    if status != INTENT_RECORDED:
        return _unregistered_launch(intent=intent, graded=graded, status=status)
    return _attached_launch(
        intent=intent,
        graded=graded,
        obligation_store_root=obligation_store_root,
        effect=effect,
        now=now,
    )


def _refused_launch(*, intent: LaunchIntent, graded: CoverageVerdict) -> LaunchVerdict:
    """The uncovered refusal: no record written, no effect performed."""
    return LaunchVerdict(
        state=(
            LAUNCH_UNOBSERVABLE if graded.state == COVERAGE_UNOBSERVABLE else LAUNCH_UNMONITORED
        ),
        operation_id=intent.operation_id,
        coverage_state=graded.state,
        diagnostic=graded.diagnostic,
        target=None,
    )


def _unregistered_launch(
    *, intent: LaunchIntent, graded: CoverageVerdict, status: str
) -> LaunchVerdict:
    """A launch whose obligation this call did not write, so it performs none.

    The two statuses mean different things and both forbid the effect. An
    ALREADY-RECORDED intent may already have produced one, so this is
    `attachment-pending` and reconciliation owns it. An UNAVAILABLE store means
    nothing durable exists, so launching would create an untracked target.
    """
    already = status == ATTACH_ALREADY_ATTACHED or status != INTENT_RECORDED and _is_recorded(
        status=status
    )
    return LaunchVerdict(
        state=LAUNCH_ATTACHMENT_PENDING if already else LAUNCH_REGISTRATION_UNAVAILABLE,
        operation_id=intent.operation_id,
        coverage_state=graded.state,
        diagnostic=(
            DIAGNOSTIC_INTENT_ALREADY_RECORDED if already else DIAGNOSTIC_INTENT_UNAVAILABLE
        ),
        target=None,
    )


def _is_recorded(*, status: str) -> bool:
    from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
        INTENT_ALREADY_RECORDED,
    )

    return status == INTENT_ALREADY_RECORDED


def _attached_launch(
    *,
    intent: LaunchIntent,
    graded: CoverageVerdict,
    obligation_store_root: Path,
    effect: LaunchEffect,
    now: float,
) -> LaunchVerdict:
    """Perform the effect and attach it, reporting protection only once attached."""
    target = effect(operation_id=intent.operation_id)
    if target is None:
        return LaunchVerdict(
            state=LAUNCH_ATTACHMENT_PENDING,
            operation_id=intent.operation_id,
            coverage_state=graded.state,
            diagnostic=DIAGNOSTIC_TARGET_UNOBSERVED,
            target=None,
        )
    status = attach_launch_target(
        obligation_store_root=obligation_store_root,
        operation_id=intent.operation_id,
        target=target,
        attached_at=now,
    )
    attached = status == ATTACH_ATTACHED
    return LaunchVerdict(
        state=LAUNCH_PROTECTED if attached else LAUNCH_ATTACHMENT_PENDING,
        operation_id=intent.operation_id,
        coverage_state=graded.state,
        diagnostic=None if attached else DIAGNOSTIC_ATTACHMENT_UNAVAILABLE,
        target=target if attached else None,
    )


def protected_completion(
    *,
    coverage: CoverageReading,
    obligation_store_root: Path,
) -> CompletionVerdict:
    """Verify this turn's durable obligations and their independent owner."""
    census = outstanding_obligations(obligation_store_root=obligation_store_root)
    outstanding = tuple(
        cast("str", record["operation_id"]) for record in census.records
    )
    if census.diagnostics:
        return CompletionVerdict(
            state=COMPLETION_UNOBSERVABLE,
            coverage_state=COVERAGE_UNOBSERVABLE,
            diagnostic=census.diagnostics[0],
            outstanding_operation_ids=outstanding,
        )
    graded = coverage_verdict(reading=coverage)
    if graded.verified:
        return CompletionVerdict(
            state=COMPLETION_PROTECTED,
            coverage_state=graded.state,
            diagnostic=None,
            outstanding_operation_ids=outstanding,
        )
    return CompletionVerdict(
        state=(
            COMPLETION_UNOBSERVABLE
            if graded.state == COVERAGE_UNOBSERVABLE
            else COMPLETION_UNMONITORED
        ),
        coverage_state=graded.state,
        diagnostic=graded.diagnostic,
        outstanding_operation_ids=outstanding,
    )
