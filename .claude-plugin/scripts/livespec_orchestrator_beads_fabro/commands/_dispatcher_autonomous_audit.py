"""Full autonomous mode — the per-decision audit record + published read surface (S2).

Full autonomous mode (specified in `SPECIFICATION/spec.md`,
`SPECIFICATION/contracts.md`, and `SPECIFICATION/constraints.md`) MUST record
every decision it auto-resolves on the EXISTING Dispatcher journal — the same
journal -> Honeycomb leg the calibration telemetry rides — carrying at minimum
the work-item id, which gate was collapsed (`approve` / `acceptance` /
`needs-human`), and what the LLM decided; no auto-resolution may be silent. The
set of decisions the mode escalated as truly-unresolvable MUST be queryable
from that same journal. This journal is the plugin's PUBLISHED per-decision
audit surface: the Control-Plane console reads each auto-resolution and each
truly-unresolvable escalation from it through the read surface here.

This module owns the RECORD CONTRACT and its read surface only — it makes NO
decision. `autonomous_decision_journal_record` is the pure builder the
decision stages (the two-valve collapse and the needs-human resolution stage,
later slices) call to journal every decision; `read_autonomous_decisions` is
the fail-open reader the console calls to observe the auto-resolutions and the
truly-unresolvable escalations. The record shape mirrors
`_dispatcher_calibration.calibration_journal_record`: a flat `stage` +
sibling-scalar dict, so the OTLP enrich stage promotes each field to a span
attribute without unwrapping a nested map. Autonomous-mode auto-resolution
disposes of already-filed items only and MUST NOT create net-new work-items;
this record surface carries dispositions, never new items.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "AUTONOMOUS_DECISION_STAGE",
    "AutonomousAudit",
    "AutonomousDecision",
    "autonomous_decision_journal_record",
    "read_autonomous_decisions",
]

# The journal `stage` marker for a per-decision autonomous-mode audit record —
# distinct from S1's `autonomous-armed` arming marker and from `calibration`.
AUTONOMOUS_DECISION_STAGE = "autonomous-decision"

# The three human-delegable gates a decision can collapse, exactly as the
# contract enumerates them.
_GATE_APPROVE = "approve"
_GATE_ACCEPTANCE = "acceptance"
_GATE_NEEDS_HUMAN = "needs-human"
_GATES = (_GATE_APPROVE, _GATE_ACCEPTANCE, _GATE_NEEDS_HUMAN)

# The two dispositions: the engine auto-resolved the decision, or it left the
# decision escalated as truly-unresolvable for a human.
_DISPOSITION_AUTO_RESOLVED = "auto-resolved"
_DISPOSITION_ESCALATED = "escalated"
_DISPOSITIONS = (_DISPOSITION_AUTO_RESOLVED, _DISPOSITION_ESCALATED)


@dataclass(frozen=True, kw_only=True)
class AutonomousDecision:
    """One per-decision autonomous-mode audit entry read back off the journal.

    `work_item_id` names the disposed item; `gate` is the collapsed gate
    (`approve` / `acceptance` / `needs-human`); `decision` is what the LLM
    decided; `disposition` is `auto-resolved` (the engine resolved it) or
    `escalated` (left truly-unresolvable for a human).
    """

    work_item_id: str
    gate: str
    decision: str
    disposition: str


@dataclass(frozen=True, kw_only=True)
class AutonomousAudit:
    """The published read view of the autonomous per-decision journal records.

    `auto_resolutions` and `escalations` are the two disposition buckets the
    console observes — every auto-resolution and every truly-unresolvable
    escalation the run journaled, split by disposition and preserving journal
    order within each bucket.
    """

    auto_resolutions: tuple[AutonomousDecision, ...]
    escalations: tuple[AutonomousDecision, ...]


def autonomous_decision_journal_record(
    *, work_item_id: str, gate: str, decision: str, disposition: str
) -> dict[str, object]:
    """Build the canonical per-decision autonomous audit journal record.

    The single dict a decision stage appends to the existing journal so the
    OTLP enrich leg ships it to Honeycomb and the console reads it back. Names
    the stage `autonomous-decision` and rides every field as a sibling scalar
    (mirroring `calibration_journal_record`). `gate` MUST be one of
    `approve` / `acceptance` / `needs-human` and `disposition` one of
    `auto-resolved` / `escalated`; an out-of-range value is a programmer bug
    (a decision stage passing an unknown gate/disposition), raised as
    `ValueError` rather than silently journaled — no auto-resolution may be
    silent, and a malformed one must not masquerade as valid.
    """
    if gate not in _GATES:
        msg = f"unknown gate {gate!r} (expected one of {_GATES})"
        raise ValueError(msg)
    if disposition not in _DISPOSITIONS:
        msg = f"unknown disposition {disposition!r} (expected one of {_DISPOSITIONS})"
        raise ValueError(msg)
    return {
        "stage": AUTONOMOUS_DECISION_STAGE,
        "work_item_id": work_item_id,
        "gate": gate,
        "decision": decision,
        "disposition": disposition,
    }


def read_autonomous_decisions(*, journal_path: Path) -> AutonomousAudit:
    """Read the published autonomous per-decision audit view from the journal.

    Fail-open, mirroring the mechanical reflection reader: a missing or
    unreadable journal file yields an empty audit, and a malformed line — bad
    JSON, a non-object, a record missing a required field, or an out-of-range
    gate/disposition — is skipped rather than raising. Only
    `autonomous-decision` stage records are considered; every other stage
    (arming, calibration, dispatch) is ignored. Records split into
    `auto_resolutions` and `escalations` by disposition, preserving journal
    order within each bucket.
    """
    auto_resolutions: list[AutonomousDecision] = []
    escalations: list[AutonomousDecision] = []
    try:
        lines = journal_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        # A missing OR an exists-but-unreadable journal fails open to an empty
        # audit, honoring the fail-open contract in the docstring above.
        lines = []
    for line in lines:
        decision = _decision_from_line(line=line)
        if decision is None:
            continue
        if decision.disposition == _DISPOSITION_ESCALATED:
            escalations.append(decision)
        else:
            auto_resolutions.append(decision)
    return AutonomousAudit(auto_resolutions=tuple(auto_resolutions), escalations=tuple(escalations))


def _decision_from_line(*, line: str) -> AutonomousDecision | None:
    """Parse one journal line into an AutonomousDecision, or None if not one.

    Returns None for malformed JSON, a non-object, a non-`autonomous-decision`
    stage, or a record whose required fields are absent or out of range — so
    the reader skips it fail-open.
    """
    try:
        parsed: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    record = {str(key): value for key, value in cast("dict[object, object]", parsed).items()}
    if record.get("stage") != AUTONOMOUS_DECISION_STAGE:
        return None
    work_item_id = record.get("work_item_id")
    gate = record.get("gate")
    decision = record.get("decision")
    disposition = record.get("disposition")
    if (
        isinstance(work_item_id, str)
        and isinstance(gate, str)
        and gate in _GATES
        and isinstance(decision, str)
        and isinstance(disposition, str)
        and disposition in _DISPOSITIONS
    ):
        return AutonomousDecision(
            work_item_id=work_item_id, gate=gate, decision=decision, disposition=disposition
        )
    return None
