"""Plan archive membership helpers, and the context a fresh reviewer is handed.

The archive completeness gate refuses disposal while any linked plan member is
undisposed. Membership comes from `parent-child` and `tracks` edges pointing to
the epic. The same gate also counts upstream `blocks` dependencies carried by
the epic as blockers that must be disposed before archive; `supersedes` edges
are deliberately ignored because supersession is not plan membership or a
blocking prerequisite.

The EVIDENCE RECORD that same gate reads is a different concern and lives in
`_plan_completeness_evidence`: the comment a reviewer writes, the parse that
reads it back, and the grade that decides whether it satisfies the leg.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
from livespec_orchestrator_beads_fabro.commands._plan_child_edges import (
    bd_child_surface_mismatch_ids,
    blocking_dependency_ids,
    has_blocks_edge_to_epic,
    is_blocks_dependency_edge,
    is_blocks_edge_to_epic,
    linked_plan_gate_ids_for_epic,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "ArchiveCompletenessReviewRequest",
    "CompletenessReviewLauncher",
    "archive_completeness_review_request",
    "bd_child_surface_mismatch_ids",
    "blocking_dependency_ids",
    "has_blocks_edge_to_epic",
    "is_blocks_dependency_edge",
    "is_blocks_edge_to_epic",
    "undisposed_plan_child_ids",
]


@dataclass(frozen=True, kw_only=True)
class ArchiveCompletenessReviewRequest:
    """Context handed to a fresh independent plan completeness reviewer."""

    project_root: Path
    slug: str
    epic_id: str
    child_ids: tuple[str, ...]
    research_paths: tuple[str, ...]


class CompletenessReviewLauncher(Protocol):
    """Callable seam that commissions one external completeness review."""

    def __call__(self, *, request: ArchiveCompletenessReviewRequest) -> str | None:
        """Launch the reviewer and return its durable evidence id, if any."""
        ...


def archive_completeness_review_request(
    *,
    client: BeadsClient,
    project_root: Path,
    source: Path,
    slug: str,
    epic_id: str,
) -> ArchiveCompletenessReviewRequest:
    """Build the request context for a fresh archive completeness reviewer."""
    return ArchiveCompletenessReviewRequest(
        project_root=project_root,
        slug=slug,
        epic_id=epic_id,
        child_ids=_disposed_child_ids(client=client, epic_id=epic_id),
        research_paths=_research_paths(project_root=project_root, source=source),
    )


def undisposed_plan_child_ids(*, client: BeadsClient, epic_id: str) -> tuple[str, ...]:
    """Return sorted plan-child ids whose ledger status is not closed."""
    return tuple(
        sorted(record["id"] for record in _undisposed_plan_children(client=client, epic_id=epic_id))
    )


def _undisposed_plan_children(*, client: BeadsClient, epic_id: str) -> list[BeadsRecord]:
    return [
        record
        for record in _plan_archive_gate_records(client=client, epic_id=epic_id)
        if _is_undisposed_plan_child(record=record)
    ]


def _plan_archive_gate_records(*, client: BeadsClient, epic_id: str) -> list[BeadsRecord]:
    records = client.list_issues()
    linked_ids = linked_plan_gate_ids_for_epic(records=records, epic_id=epic_id)
    return [
        record
        for record in records
        if isinstance(issue_id := record.get("id"), str) and issue_id in linked_ids
    ]


def _disposed_child_ids(*, client: BeadsClient, epic_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            record["id"]
            for record in _plan_archive_gate_records(client=client, epic_id=epic_id)
            if isinstance(record.get("id"), str) and record.get("status") == "closed"
        )
    )


def _research_paths(*, project_root: Path, source: Path) -> tuple[str, ...]:
    research_dir = source / "research"
    if not research_dir.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(project_root).as_posix()
            for path in research_dir.rglob("*")
            if path.is_file()
        )
    )


def _is_undisposed_plan_child(*, record: BeadsRecord) -> bool:
    issue_id = record.get("id")
    return isinstance(issue_id, str) and record.get("status") != "closed"
