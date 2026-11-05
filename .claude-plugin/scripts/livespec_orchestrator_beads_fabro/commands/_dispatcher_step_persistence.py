"""Cross-dispatch persistence of a degraded post-merge step outcome.

A degraded outcome that only ever affected the dispatch that produced it would
degrade silently on every dispatch forever: the janitor never runs, nobody is
refused, and the missing integration point is never provided. So the degradation
PERSISTS -- the journal is the durable carrier, and the NEXT dispatch for the
repository reads it back and refuses at the pre-dispatch gate until either a
re-verification observes the integration point provided or a committed waiver
covers the step. The hard refusal IS the mechanism that makes the adopter
provide the missing piece.

THE JOURNAL IS THE STATE, deliberately. The alternative -- a sidecar marker file
-- would be a second source of truth that can disagree with the record everyone
audits, and would need its own lifecycle. The journal already carries every
outcome, is append-only, and is what an operator reads; reading it back costs one
pass over a file this dispatch is about to append to anyway.

WHY THE CLEARING IS ITS OWN RECORD rather than the absence of a later
degradation. A refusal that ended by nothing happening would be unauditable: an
operator asking "why did this start dispatching again?" would find no answer.
The clearing record names the step identifier and the degraded outcome record it
clears, so the refusal's end is as durable as its start.

An outcome record is addressed by the envelope timestamp the append layer
stamps, together with the work-item it belongs to. That reference is stable
because the journal is append-only: the line it names never moves and is never
rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import (
    snapshot_records_for_stages,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import STEP_IDS
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = [
    "CLEARING_STAGE",
    "PERSISTENCE_STAGE",
    "DegradedStepOutcome",
    "clearing_record",
    "outstanding_degraded_step",
    "persistence_refusal_detail",
    "persistence_refusal_record",
]

PERSISTENCE_STAGE = "step-persistence-preflight"
CLEARING_STAGE = "step-clearing"

_OUTCOME_STAGE = "outcome"
_REASON_PERSISTS = "degraded-step-outcome-persists"
_REASON_CLEARED = "degraded-step-integration-point-provided"

_UNKNOWN = "<unknown>"


@dataclass(frozen=True, kw_only=True)
class DegradedStepOutcome:
    """One degraded post-merge outcome read back out of the journal.

    `reference` is the durable address of the originating record -- what the
    refusal names and what the clearing record clears. It is carried as a field
    rather than derived at each use so the refusal and the clearing cannot
    render the same record two different ways.
    """

    step: str
    at: str
    work_item_id: str
    missing_integration_point: str
    remedy: str
    reference: str


def outstanding_degraded_step(*, journal_path: Path) -> DegradedStepOutcome | None:
    """The newest degraded outcome no clearing record has cleared, or None.

    Newest rather than oldest because a repository that degraded, was cleared,
    and degraded again must refuse on the CURRENT degradation; and a waived
    proceed is deliberately not a clearing, so a standing waiver keeps naming
    what it waives on every dispatch.
    """
    records = _records(path=journal_path)
    cleared = {
        str(record.get("clears_outcome_at"))
        for record in records
        if record.get("stage") == CLEARING_STAGE
    }
    outstanding = [
        degraded for degraded in _degraded_outcomes(records=records) if degraded.at not in cleared
    ]
    if not outstanding:
        return None
    return outstanding[-1]


def clearing_record(*, degraded: DegradedStepOutcome) -> dict[str, object]:
    """The durable record that a passing re-verification ends this refusal."""
    return {
        "stage": CLEARING_STAGE,
        "step": degraded.step,
        "terminal": False,
        "status": "cleared",
        "reason": _REASON_CLEARED,
        "integration_point": degraded.missing_integration_point,
        "clears_outcome_record": degraded.reference,
        "clears_outcome_at": degraded.at,
        "clears_work_item_id": degraded.work_item_id,
    }


def persistence_refusal_record(
    *, degraded: DegradedStepOutcome, resolution: str | None = None
) -> dict[str, object]:
    """The journal record of the pre-dispatch gate refusing on a standing degradation.

    `resolution` is the re-verification's account of WHICH resolution it
    attempted, carried by the steps whose integration point is declaration-
    resolved and absent for the steps that verify themselves. It is journaled
    beside the refusal, not only printed, so an operator reading the record
    later can still tell "your recipe is missing" from "I looked for a recipe
    you never declared".
    """
    record: dict[str, object] = {
        "stage": PERSISTENCE_STAGE,
        "step": degraded.step,
        "terminal": True,
        "status": "failed",
        "reason": _REASON_PERSISTS,
        "missing_integration_point": degraded.missing_integration_point,
        "originating_outcome_record": degraded.reference,
        "remedy": degraded.remedy,
    }
    if resolution is not None:
        record["resolution_attempted"] = resolution
    return record


def persistence_refusal_detail(
    *, degraded: DegradedStepOutcome, resolution: str | None = None
) -> str:
    """The operator-facing refusal: what is missing, which record said so, the way out."""
    attempted = "" if resolution is None else f"{resolution}\n"
    return (
        f"ERROR: a degraded `{degraded.step}` outcome for this repository is still "
        "outstanding; refusing dispatch before sandbox work.\n"
        f"Missing required integration point: {degraded.missing_integration_point}\n"
        f"Originating outcome record: {degraded.reference}\n"
        f"{attempted}"
        f"Remedy: {degraded.remedy}\n"
    )


def _records(*, path: Path) -> list[dict[str, Any]]:
    """Every parseable JSONL record in the journal; an absent journal has none."""
    snapshot = snapshot_records_for_stages(
        journal_path=path, stages=(_OUTCOME_STAGE, CLEARING_STAGE)
    )
    if snapshot is not None:
        # The pass snapshot already parsed this file; copy only the outer list
        # because the persistence calculation filters it without mutating records.
        return [cast("dict[str, Any]", record) for record in snapshot]
    if not path.is_file():
        return []
    loaded = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(loaded, AttemptFailure):
        return []
    parsed = (_record(line=line) for line in loaded.splitlines())
    return [record for record in parsed if record is not None]


def _record(*, line: str) -> dict[str, Any] | None:
    parsed = parse_json(text=line)
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, Any]", parsed)


def _degraded_outcomes(*, records: list[dict[str, Any]]) -> list[DegradedStepOutcome]:
    found: list[DegradedStepOutcome] = []
    for record in records:
        outcome = record.get("outcome")
        if record.get("stage") != _OUTCOME_STAGE or not isinstance(outcome, dict):
            continue
        degraded = _degraded(record=record, outcome=cast("dict[str, Any]", outcome))
        if degraded is not None:
            found.append(degraded)
    return found


def _degraded(*, record: dict[str, Any], outcome: dict[str, Any]) -> DegradedStepOutcome | None:
    """One outcome payload, when it is a degraded record of a vocabulary step.

    All three of the structured fields are required together: a payload naming a
    step but no integration point cannot be re-verified, and refusing on it
    would produce a refusal with nothing actionable in it.
    """
    step = outcome.get("step")
    if not isinstance(step, str) or step not in STEP_IDS:
        return None
    point = outcome.get("missing_integration_point")
    remedy = outcome.get("remedy")
    if not isinstance(point, str) or not isinstance(remedy, str):
        return None
    at = str(record.get("at", _UNKNOWN))
    work_item_id = str(outcome.get("work_item_id", _UNKNOWN))
    return DegradedStepOutcome(
        step=step,
        at=at,
        work_item_id=work_item_id,
        missing_integration_point=point,
        remedy=remedy,
        reference=f"stage={_OUTCOME_STAGE} at={at} work_item_id={work_item_id} step={step}",
    )
