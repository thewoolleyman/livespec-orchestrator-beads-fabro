"""Classify completed dispatch attempts before an item is claimed again.

The factory reader supplies each attempt's milestone position from the workflow
dependency graph.  This module deliberately never compares stage names: they
are operator-facing evidence, while ``high_water_order`` is the graph-derived
ordering used for the admission decision.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CompletedAttempt",
    "RedispatchProgressDecision",
    "RedispatchProgressRefusal",
    "RedispatchRecovery",
    "redispatch_progress_decision",
]

_POLICY_NAME = "dispatcher.redispatch_no_progress_limit"


@dataclass(frozen=True, kw_only=True)
class CompletedAttempt:
    """One factory-observed run, classified before the admission gate reads it."""

    run_id: str
    terminal_cause: str
    high_water_milestone: str
    item_attributable: bool | None
    workflow_identity: str = "default"
    high_water_order: int = 0
    completed: bool = True
    diagnosed: bool = False


@dataclass(frozen=True, kw_only=True)
class RedispatchRecovery:
    """A one-use, typed causal recovery authorization for a flat epoch.

    The admission reader validates this record before passing it to the
    progress decision.  Keeping the identity and the history it addresses
    together makes a later gate able to reject a replay instead of treating
    prose about a changed approach as a reset.
    """

    attempt_id: str
    prior_run_ids: tuple[str, ...]
    diagnosis: str
    operation: str
    execution_evidence: str


@dataclass(frozen=True, kw_only=True)
class RedispatchProgressRefusal:
    """The evidence an operator needs to diagnose a repeated flat history."""

    run_ids: tuple[str, ...]
    causes: tuple[str, ...]
    high_water_milestone: str


@dataclass(frozen=True, kw_only=True)
class RedispatchProgressDecision:
    """A refusal, a diagnosis requirement, or the currently flat run ids."""

    refusal: RedispatchProgressRefusal | None
    diagnosis: str | None
    non_progress_run_ids: tuple[str, ...]
    authorized_recovery_attempt_id: str | None = None
    diagnosis_run_id: str | None = None


def redispatch_progress_decision(
    *,
    limit: int | None,
    attempts: tuple[CompletedAttempt, ...],
    recovery: RedispatchRecovery | None = None,
    consumed_recovery_attempt_ids: frozenset[str] = frozenset(),
) -> RedispatchProgressDecision:
    """Apply the prior-high-water rule to one item's observed attempt history.

    The first completed terminal establishes the baseline.  Only later,
    comparable item-attributable terminals at or below that prior mark consume
    the limit.  A higher graph position starts a new consecutive sequence;
    host failures leave it untouched.  An unknown cause or workflow variant is
    a diagnosis, never an inferred host failure.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return _diagnosis(detail=f"{_POLICY_NAME} must be a positive integer")
    seen: set[str] = set()
    history: list[str] = []
    baseline: CompletedAttempt | None = None
    flat: list[CompletedAttempt] = []
    for attempt in attempts:
        if not attempt.completed or attempt.run_id in seen:
            continue
        seen.add(attempt.run_id)
        history.append(attempt.run_id)
        if attempt.diagnosed:
            baseline = attempt
            flat = []
            continue
        if attempt.item_attributable is None:
            return _diagnosed(
                run_id=attempt.run_id,
                detail=f"{attempt.run_id} has an unknown terminal cause",
                history=tuple(history),
                recovery=recovery,
                consumed_recovery_attempt_ids=consumed_recovery_attempt_ids,
            )
        if baseline is None:
            baseline = attempt
            continue
        if attempt.workflow_identity != baseline.workflow_identity:
            return _diagnosed(
                run_id=attempt.run_id,
                detail=f"{attempt.run_id} uses incomparable workflow {attempt.workflow_identity}",
                history=tuple(history),
                recovery=recovery,
                consumed_recovery_attempt_ids=consumed_recovery_attempt_ids,
            )
        if not attempt.item_attributable:
            continue
        if attempt.high_water_order > baseline.high_water_order:
            baseline = attempt
            flat = []
            continue
        flat.append(attempt)
    return _conclusion(
        baseline=baseline,
        flat=tuple(flat),
        limit=limit,
        recovery=recovery,
        consumed_recovery_attempt_ids=consumed_recovery_attempt_ids,
    )


def _conclusion(
    *,
    baseline: CompletedAttempt | None,
    flat: tuple[CompletedAttempt, ...],
    limit: int,
    recovery: RedispatchRecovery | None,
    consumed_recovery_attempt_ids: frozenset[str],
) -> RedispatchProgressDecision:
    """Refuse once the flat run reaches the limit; otherwise report the count."""
    if baseline is None or len(flat) < limit:
        return RedispatchProgressDecision(
            refusal=None,
            diagnosis=None,
            non_progress_run_ids=tuple(entry.run_id for entry in flat),
        )
    refusal = RedispatchProgressRefusal(
        run_ids=tuple(entry.run_id for entry in flat),
        causes=tuple(entry.terminal_cause for entry in flat),
        high_water_milestone=baseline.high_water_milestone,
    )
    return _recovery_decision(
        refusal=refusal,
        recovery=recovery,
        consumed_recovery_attempt_ids=consumed_recovery_attempt_ids,
    )


def _diagnosis(*, detail: str, run_id: str | None = None) -> RedispatchProgressDecision:
    return RedispatchProgressDecision(
        refusal=None, diagnosis=detail, non_progress_run_ids=(), diagnosis_run_id=run_id
    )


def _diagnosed(
    *,
    run_id: str,
    detail: str,
    history: tuple[str, ...],
    recovery: RedispatchRecovery | None,
    consumed_recovery_attempt_ids: frozenset[str],
) -> RedispatchProgressDecision:
    """A diagnosis stands unless one fresh typed recovery names the whole history.

    Without this exit an unknown cause or an incomparable variant would refuse
    every later dispatch of the item, because nothing could ever make it known.
    """
    if recovery is None:
        return _diagnosis(detail=detail, run_id=run_id)
    invalid = _missing_recovery_field(recovery=recovery)
    if invalid is None and recovery.prior_run_ids != history:
        invalid = "causal recovery must name the diagnosed run history"
    if invalid is not None:
        return _diagnosis(detail=invalid, run_id=run_id)
    if recovery.attempt_id in consumed_recovery_attempt_ids:
        return _diagnosis(detail=detail, run_id=run_id)
    return RedispatchProgressDecision(
        refusal=None,
        diagnosis=None,
        non_progress_run_ids=(),
        authorized_recovery_attempt_id=recovery.attempt_id,
    )


def _recovery_decision(
    *,
    refusal: RedispatchProgressRefusal,
    recovery: RedispatchRecovery | None,
    consumed_recovery_attempt_ids: frozenset[str],
) -> RedispatchProgressDecision:
    """Permit one refused epoch only when its typed recovery is fresh and causal."""
    if recovery is None:
        return RedispatchProgressDecision(
            refusal=refusal,
            diagnosis=None,
            non_progress_run_ids=refusal.run_ids,
        )
    invalid = _invalid_recovery(recovery=recovery, refusal=refusal)
    if invalid is not None:
        return _diagnosis(detail=invalid)
    if recovery.attempt_id in consumed_recovery_attempt_ids:
        return RedispatchProgressDecision(
            refusal=refusal,
            diagnosis=None,
            non_progress_run_ids=refusal.run_ids,
        )
    return RedispatchProgressDecision(
        refusal=None,
        diagnosis=None,
        non_progress_run_ids=refusal.run_ids,
        authorized_recovery_attempt_id=recovery.attempt_id,
    )


def _invalid_recovery(
    *, recovery: RedispatchRecovery, refusal: RedispatchProgressRefusal
) -> str | None:
    """Return the missing causal field, without accepting prose-only recovery."""
    missing = _missing_recovery_field(recovery=recovery)
    if missing is not None:
        return missing
    if recovery.prior_run_ids != refusal.run_ids:
        return "causal recovery must name the refused non-progress run history"
    return None


def _missing_recovery_field(*, recovery: RedispatchRecovery) -> str | None:
    fields = (
        ("attempt id", recovery.attempt_id),
        ("measured diagnosis", recovery.diagnosis),
        ("executable operation", recovery.operation),
        ("execution evidence", recovery.execution_evidence),
    )
    for name, value in fields:
        if value.strip() == "":
            return f"causal recovery requires {name}"
    return None
