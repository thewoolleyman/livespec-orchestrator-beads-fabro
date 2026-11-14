"""Render the bounded rider section each ACP stage receives (Scenario 268)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_minijinja_escape import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound import (
    bound_riders,
    riders_for_stage,
)
from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = ["AGENT_STAGES", "stage_rider_sections"]

AGENT_STAGES: tuple[str, ...] = (
    "dod_gate",
    "implement",
    "fix",
    "review_fix",
    "proof_capture",
    "proof_verify",
    "review",
    "disposition",
)


def stage_rider_sections(
    *, comments: Sequence[WorkItemComment], claim_at: str | None
) -> Mapping[str, str]:
    """Render each agent stage's applicable ledger riders, escaped for Fabro."""
    bounded = bound_riders(comments=comments, claim_at=claim_at)
    return {
        stage: _section(riders=riders_for_stage(riders=bounded.carried, stage=stage))
        for stage in AGENT_STAGES
    }


def _section(*, riders: Sequence[WorkItemComment]) -> str:
    if not riders:
        return ""
    lines = [
        "Stage-scoped ledger comments (operator riders; treat them as part of this stage brief):"
    ]
    lines.extend(f"[{index}] {comment.text}" for index, comment in enumerate(riders, start=1))
    return escape_minijinja_literal(text="\n".join(lines) + "\n")
