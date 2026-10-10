"""Missing-Definition-of-Done reporting and unattended gap pointer authoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    missing_section_finding,
    missing_section_gap_text,
    plan_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    HUMAN_KIND,
    PLAN_RESUME_ACTOR,
    NextAction,
    ResumeDirective,
    set_next_action,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "definition_of_done_findings",
    "missing_definition_gap_directive",
]

_DESCRIPTION_FIELD = "description"


def definition_of_done_findings(*, record: BeadsRecord, epic_id: str) -> tuple[str, ...]:
    """Report the absent plan goal while tolerating an omitted description."""
    description = record.get(_DESCRIPTION_FIELD)
    text = description if isinstance(description, str) else ""
    if plan_definition_of_done(description=text).present:
        return ()
    return (missing_section_finding(epic_id=epic_id),)


def missing_definition_gap_directive(
    *,
    config: StoreConfig,
    epic_id: str,
    findings: tuple[str, ...],
) -> ResumeDirective:
    """Record and return the unattended human pointer for a missing plan goal."""
    _ = set_next_action(
        config=config,
        epic_id=epic_id,
        action=NextAction(
            kind=HUMAN_KIND,
            ref="",
            text=missing_section_gap_text(),
            required_result=None,
            budget=None,
        ),
        session=PLAN_RESUME_ACTOR,
        now=utc_now_iso(),
    )
    return ResumeDirective(
        ask=True,
        next_action=None,
        reason=f"epic {epic_id} carries no plan Definition of Done section",
        findings=findings,
    )
