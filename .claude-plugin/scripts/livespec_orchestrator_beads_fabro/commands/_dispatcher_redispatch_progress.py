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


def redispatch_progress_decision(
    *, limit: int | None, attempts: tuple[CompletedAttempt, ...]
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
    baseline: CompletedAttempt | None = None
    flat: list[CompletedAttempt] = []
    for attempt in attempts:
        if not attempt.completed or attempt.run_id in seen:
            continue
        seen.add(attempt.run_id)
        if attempt.item_attributable is None:
            return _diagnosis(detail=f"{attempt.run_id} has an unknown terminal cause")
        if baseline is None:
            baseline = attempt
            continue
        if attempt.workflow_identity != baseline.workflow_identity:
            return _diagnosis(
                detail=(f"{attempt.run_id} uses incomparable workflow {attempt.workflow_identity}")
            )
        if not attempt.item_attributable:
            continue
        if attempt.high_water_order > baseline.high_water_order:
            baseline = attempt
            flat = []
            continue
        flat.append(attempt)
        if len(flat) >= limit:
            return RedispatchProgressDecision(
                refusal=RedispatchProgressRefusal(
                    run_ids=tuple(entry.run_id for entry in flat),
                    causes=tuple(entry.terminal_cause for entry in flat),
                    high_water_milestone=baseline.high_water_milestone,
                ),
                diagnosis=None,
                non_progress_run_ids=tuple(entry.run_id for entry in flat),
            )
    return RedispatchProgressDecision(
        refusal=None,
        diagnosis=None,
        non_progress_run_ids=tuple(entry.run_id for entry in flat),
    )


def _diagnosis(*, detail: str) -> RedispatchProgressDecision:
    return RedispatchProgressDecision(refusal=None, diagnosis=detail, non_progress_run_ids=())
