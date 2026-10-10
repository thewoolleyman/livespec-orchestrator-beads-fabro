"""Plan primitives backed by ledger-held handoff comments.

The AUTHORING half of the plan operation: creating a plan, appending a handoff
entry, and recording a scope event. The ARCHIVE leg is its own cohesive module,
`_plan_archive`, and is re-exported here so every existing caller is unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_anchor import plan_anchor_epic
from livespec_orchestrator_beads_fabro.commands._plan_archive import archive_thread
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
    outside_plan_path_references,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
    blocking_dependency_ids,
    is_blocks_dependency_edge,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import PlanCarrierMapRefusedError
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    current_continuation_ruling,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
    plan_research_note,
)
from livespec_orchestrator_beads_fabro.commands._plan_disposition import (
    PlanDispositionRefusedError,
    close_plan_child,
    reparent_plan_child,
)
from livespec_orchestrator_beads_fabro.commands._plan_handoff import (
    append_handoff,
    append_supervisor_handoff,
)
from livespec_orchestrator_beads_fabro.commands._plan_identity import (
    tag_epic_plan_slug,
    write_plan_anchor,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_KINDS,
    NextAction,
    NextActionRefusal,
    ResumeDirective,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_record_rate import (
    DEFAULT_DAILY_RECORD_THRESHOLD,
    PlanRecordRateWarning,
    plan_record_rate_warnings,
)
from livespec_orchestrator_beads_fabro.commands._plan_scope_event import (
    PlanContinuationAuthorization,
    PlanContinuationRefusal,
    PlanContinuationRevocation,
    PlanContinuationWrite,
    ScopeEventWrite,
    write_scope_event,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    UNATTENDED_ENV_VAR,
    PlanTimelineEntry,
    handoff_timeline_findings,
    is_unattended_session,
    read_timeline,
    recorded_next_actions,
)
from livespec_orchestrator_beads_fabro.store import append_work_item

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DEFAULT_DAILY_RECORD_THRESHOLD",
    "NEXT_ACTION_KINDS",
    "PLAN_HANDOFF_PREFIX",
    "UNATTENDED_ENV_VAR",
    "NextAction",
    "NextActionRefusal",
    "PlanArchiveRefusedError",
    "PlanCarrierMapRefusedError",
    "PlanContinuationAuthorization",
    "PlanContinuationRefusal",
    "PlanContinuationRevocation",
    "PlanDefinitionOfDone",
    "PlanDispositionRefusedError",
    "PlanRecordRateWarning",
    "PlanTimelineEntry",
    "ResumeDirective",
    "_blocking_dependency_ids",
    "_is_blocks_dependency_edge",
    "append_handoff",
    "append_supervisor_handoff",
    "archive_thread",
    "close_plan_child",
    "create_thread",
    "current_continuation_ruling",
    "handoff_timeline_findings",
    "is_unattended_session",
    "outside_plan_path_references",
    "plan_record_rate_warnings",
    "read_timeline",
    "record_completeness_review_evidence",
    "record_scope_event",
    "recorded_next_actions",
    "reparent_plan_child",
    "resume_directive",
    "set_next_action",
]

_PLAN_DIR = "plan"
_RESEARCH_DIR = "research"


def create_thread(  # noqa: PLR0913 — package primitive mirrors the plan-create inputs.
    *,
    project_root: Path,
    config: StoreConfig,
    slug: str,
    title: str,
    research_filename: str,
    research_text: str,
    now: str,
    definition_of_done: PlanDefinitionOfDone,
) -> dict[str, str]:
    """Create a plan with one research note, one ledger epic, and its anchor.

    `definition_of_done` is REQUIRED, not defaulted. The plan clause states
    outright that there is no exemption list — a plan must not archive without
    the section, whenever its epic was created — so a parameter a caller could
    omit would hand back a plan that can never be archived, and would do it
    silently at the one moment the maintainer's statement is actually available.
    """
    topic_dir = project_root / _PLAN_DIR / slug
    research_path = topic_dir / _RESEARCH_DIR / research_filename
    # Write-once is enforced on the NOTE, not on its directory: an epic may
    # adopt a `plan/<slug>/` that already holds standalone research, so the
    # directory legitimately pre-exists while the note it adds may not. The
    # exclusive-create mode refuses that collision as the directory-level
    # `exist_ok=False` used to, without refusing the adoption.
    research_path.parent.mkdir(parents=True, exist_ok=True)
    with research_path.open("x", encoding="utf-8") as handle:
        _ = handle.write(
            plan_research_note(definition=definition_of_done, research_text=research_text)
        )
    epic = plan_anchor_epic(
        prefix=config.prefix,
        slug=slug,
        title=title,
        now=now,
        definition_of_done=definition_of_done,
    )
    append_work_item(path=config, item=epic)
    _ = tag_epic_plan_slug(config=config, epic_id=epic.id, title=title, slug=slug)
    anchor_path = write_plan_anchor(project_root=project_root, slug=slug, epic_id=epic.id)
    return {
        "anchor_path": anchor_path.relative_to(project_root).as_posix(),
        "epic_id": epic.id,
        "research_path": research_path.relative_to(project_root).as_posix(),
    }


def record_scope_event(  # noqa: PLR0913 — package primitive mirrors the scope-event inputs.
    *,
    config: StoreConfig,
    epic_id: str,
    requirements: tuple[str, ...],
    deferrals: tuple[str, ...],
    author: str,
    now: str,
    carriers: tuple[str, ...] = (),
    env: Mapping[str, str] | None = None,
    continuation: PlanContinuationWrite | None = None,
) -> PlanContinuationRefusal | None:
    """Record scoped requirements and explicit deferrals before child admission.

    `continuation` makes this an attended-only authorization or revocation. The
    primitive renders its fixed first line and, for authorization, appends the
    `recorded-attended: true` evidence itself. An expected refusal is returned
    without writing when the session is unattended, a caller field spans lines,
    or the ruling is mixed with a carrier map.

    `carriers` makes an ordinary write a CARRIER-MAP event: one entry per plan assertion, in
    Definition of Done order, of the form `<ordinal>: <work-item-id>[, ...]` or
    `<ordinal>: plan-level proof`. Supplying it arms the gate that refuses an
    incomplete map. Omitting it records an ordinary requirement or deferral
    exactly as before.
    """
    return write_scope_event(
        request=ScopeEventWrite(
            config=config,
            epic_id=epic_id,
            requirements=requirements,
            deferrals=deferrals,
            author=author,
            now=now,
            carriers=carriers,
            env=env,
            continuation=continuation,
        )
    )


def _blocking_dependency_ids(*, record: BeadsRecord) -> frozenset[str]:
    return blocking_dependency_ids(record=record)


def _is_blocks_dependency_edge(*, edge: object) -> str | None:
    return is_blocks_dependency_edge(edge=edge)
