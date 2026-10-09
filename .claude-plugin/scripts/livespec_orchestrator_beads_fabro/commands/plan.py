"""Plan primitives backed by ledger-held handoff comments.

The AUTHORING half of the plan operation: creating a plan, appending a handoff
entry, and recording a scope event. The ARCHIVE leg is its own cohesive module,
`_plan_archive`, and is re-exported here so every existing caller is unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
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
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    PlanCarrierMapRefusedError,
    carrier_map_block,
    guard_carrier_map,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    record_completeness_review_evidence,
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
from livespec_orchestrator_beads_fabro.commands._plan_identity import (
    tag_epic_plan_slug,
    write_plan_anchor,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_KINDS,
    NextAction,
    ResumeDirective,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_record_rate import (
    DEFAULT_DAILY_RECORD_THRESHOLD,
    PlanRecordRateWarning,
    plan_record_rate_warnings,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    PLAN_SCOPE_PREFIX,
    UNATTENDED_ENV_VAR,
    PlanTimelineEntry,
    handoff_timeline_findings,
    is_unattended_session,
    plan_comment_body,
    read_timeline,
    recorded_next_actions,
)
from livespec_orchestrator_beads_fabro.store import append_work_item

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DEFAULT_DAILY_RECORD_THRESHOLD",
    "NEXT_ACTION_KINDS",
    "UNATTENDED_ENV_VAR",
    "NextAction",
    "PlanArchiveRefusedError",
    "PlanCarrierMapRefusedError",
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


def append_handoff(
    *,
    config: StoreConfig,
    epic_id: str,
    body: str,
    author: str,
    now: str,
    next_action: NextAction,
) -> None:
    """Append one handoff entry AND update the epic's typed next_action.

    Per contracts.md's "Ledger-held handoff persistence": the next action is
    not carried by the comment. The entry holds rationale, warnings and
    pointers; the pointer to the next step is the typed metadata written here
    in the same call, so a handoff can never record a next step the resume
    path cannot see. `author` doubles as the `last_session` identity, because
    the session that signs the entry is the one that wrote the pointer.
    """
    client = make_beads_client(config=config)
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(prefix=PLAN_HANDOFF_PREFIX, author=author, now=now, body=body),
    )
    set_next_action(
        config=config,
        epic_id=epic_id,
        action=next_action,
        session=author,
        now=now,
    )


def append_supervisor_handoff(
    *,
    config: StoreConfig,
    epic_id: str,
    slug: str,
    body: str,
    now: str,
    next_action: NextAction,
) -> None:
    """Append one handoff entry authored as the plan's reserved supervisor literal.

    Per contracts.md's "Ledger-held handoff persistence": the supervisor
    role's `author:` field MUST be `<slug>-supervisor`, computed here rather
    than accepted as a caller-supplied string, mirroring `archive_thread`'s
    `author="plan-archive"` reservation.
    """
    append_handoff(
        config=config,
        epic_id=epic_id,
        body=body,
        author=f"{slug}-supervisor",
        now=now,
        next_action=next_action,
    )


def record_scope_event(  # noqa: PLR0913 — package primitive mirrors the scope-event inputs.
    *,
    config: StoreConfig,
    epic_id: str,
    requirements: tuple[str, ...],
    deferrals: tuple[str, ...],
    author: str,
    now: str,
    carriers: tuple[str, ...] = (),
) -> None:
    """Record scoped requirements and explicit deferrals before child admission.

    `carriers` makes this a CARRIER-MAP event: one entry per plan assertion, in
    Definition of Done order, of the form `<ordinal>: <work-item-id>[, ...]` or
    `<ordinal>: plan-level proof`. Supplying it arms the gate that refuses an
    incomplete map. Omitting it records a ruling or deferral exactly as before —
    the default is empty rather than required precisely so the ruling path this
    primitive also serves is unaffected.
    """
    client = make_beads_client(config=config)
    guard_carrier_map(
        epic_id=epic_id,
        description=_epic_description(client=client, epic_id=epic_id),
        carriers=carriers,
    )
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author=author,
            now=now,
            body=_scope_body(requirements=requirements, deferrals=deferrals, carriers=carriers),
        ),
    )


def _blocking_dependency_ids(*, record: BeadsRecord) -> frozenset[str]:
    return blocking_dependency_ids(record=record)


def _is_blocks_dependency_edge(*, edge: object) -> str | None:
    return is_blocks_dependency_edge(edge=edge)


def _epic_description(*, client: BeadsClient, epic_id: str) -> str:
    """One epic's description, tolerating the key's absence.

    Beads records are `omitempty`-sparse: an epic holding no description omits
    the key entirely rather than carrying an empty string.
    """
    description = client.show_issue(issue_id=epic_id).get("description")
    return description if isinstance(description, str) else ""


def _scope_body(
    *, requirements: tuple[str, ...], deferrals: tuple[str, ...], carriers: tuple[str, ...]
) -> str:
    requirement_lines = "\n".join(f"- {requirement}" for requirement in requirements)
    deferral_lines = "\n".join(f"- {deferral}" for deferral in deferrals)
    body = f"Requirement carriers:\n{requirement_lines}\n\nExplicit deferrals:\n{deferral_lines}"
    block = carrier_map_block(carriers=carriers)
    return f"{body}\n\n{block}" if block else body
