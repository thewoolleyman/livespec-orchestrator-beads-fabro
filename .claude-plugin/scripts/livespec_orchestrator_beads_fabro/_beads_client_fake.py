"""In-memory `BeadsClient` implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import (
        BeadsRecord,
        DependencyEdge,
        IssueDraft,
    )

__all__: list[str] = [
    "FakeBeadsClient",
    "fake_singleton",
    "reset_fake_singleton",
]

_EDGE_PARENT_CHILD = "parent-child"


class FakeBeadsClient:
    """Pure in-memory `BeadsClient` — runtime fallback + hermetic test backend.

    Holds a dict of issue records keyed by id. Each record is the same
    shape a parsed `bd ... --json` issue object has, so the store layer's
    field map works identically against the fake and the shell backend.
    Writes mutate the in-memory dict; reads return copies so callers
    cannot accidentally mutate the backing store.
    """

    def __init__(self) -> None:
        self._issues: dict[str, BeadsRecord] = {}
        self._comments: dict[str, list[BeadsRecord]] = {}
        self.custom_statuses_registered: bool = False

    def list_issues(self) -> list[BeadsRecord]:
        return [dict(record) for record in self._issues.values()]

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="issue not present in the in-memory tenant",
            )
        return dict(record)

    def seed_comment(
        self,
        *,
        issue_id: str,
        text: str,
        author: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """Seed a comment onto an issue (fake-only hermetic seeding seam)."""
        if issue_id not in self._issues:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot comment on an issue that is not present in the tenant",
            )
        record: BeadsRecord = {
            "issue_id": issue_id,
            "text": text,
            "author": author,
            "created_at": created_at,
        }
        self._comments.setdefault(issue_id, []).append(record)

    def list_comments(self, *, issue_id: str) -> list[BeadsRecord]:
        """Return copies of an issue's seeded comments."""
        if issue_id not in self._issues:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="issue not present in the in-memory tenant",
            )
        return [dict(record) for record in self._comments.get(issue_id, [])]

    def children(self, *, parent_id: str) -> list[BeadsRecord]:
        return [
            dict(record)
            for record in self._issues.values()
            if _is_child_of(record=record, parent_id=parent_id)
        ]

    def exists(self, *, issue_id: str) -> bool:
        return issue_id in self._issues

    def create_issue(self, *, draft: IssueDraft) -> str:
        dependencies: list[DependencyEdge] = []
        if draft.parent_id is not None:
            dependencies.append({"depends_on_id": draft.parent_id, "type": _EDGE_PARENT_CHILD})
        record: BeadsRecord = {
            "id": draft.issue_id,
            "issue_type": draft.issue_type,
            "title": draft.title,
            "description": draft.description,
            "priority": draft.priority,
            "assignee": draft.assignee,
            "created_at": draft.created_at,
            "status": "open",
            "close_reason": None,
            "labels": list(draft.labels),
            "metadata": dict(draft.metadata),
            "spec_id": draft.spec_id,
            "parent_id": draft.parent_id,
            "dependencies": dependencies,
        }
        if draft.acceptance_criteria is not None:
            record["acceptance_criteria"] = draft.acceptance_criteria
        if draft.notes is not None:
            record["notes"] = draft.notes
        self._issues[draft.issue_id] = record
        return draft.issue_id

    def update_issue(  # noqa: PLR0913 — kw-only partial-update verb; each field is an independent optional mutation.
        self,
        *,
        issue_id: str,
        status: str | None = None,
        assignee: str | None = None,
        clear_assignee: bool = False,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        acceptance_criteria: str | None = None,
        notes: str | None = None,
        description: str | None = None,
    ) -> None:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot update an issue that is not present in the tenant",
            )
        _update_scalar_fields(
            record=record,
            fields={
                "status": status,
                "parent_id": parent_id,
                # The only field that is COPIED rather than referenced: the
                # caller's dict must not become the tenant's own.
                "metadata": None if metadata is None else dict(metadata),
                "acceptance_criteria": acceptance_criteria,
                "notes": notes,
                "description": description,
            },
        )
        _update_assignee(record=record, assignee=assignee, clear_assignee=clear_assignee)
        _add_labels(record=record, labels=add_labels)
        _remove_labels(record=record, labels=remove_labels)

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot close an issue that is not present in the tenant",
            )
        record["status"] = "closed"
        record["close_reason"] = reason

    def add_dependency(self, *, from_id: str, to_id: str, edge_type: str) -> None:
        record = self._issues.get(from_id)
        if record is None:
            raise BeadsMappingError(
                record_id=from_id,
                detail="cannot add a dependency from an issue not present in the tenant",
            )
        edges = cast("list[DependencyEdge]", record.setdefault("dependencies", []))
        edge: DependencyEdge = {"depends_on_id": to_id, "type": edge_type}
        if edge not in edges:
            edges.append(edge)

    def remove_dependency(self, *, from_id: str, to_id: str) -> None:
        """Drop every edge from one issue to another; absent edges are a no-op."""
        record = self._issues.get(from_id)
        if record is None:
            return
        edges = cast("list[DependencyEdge]", record.setdefault("dependencies", []))
        record["dependencies"] = [edge for edge in edges if edge.get("depends_on_id") != to_id]

    def add_comment(self, *, issue_id: str, body: str) -> None:
        """Append a comment in the in-memory tenant (mirrors `seed_comment`)."""
        if issue_id not in self._issues:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot comment on an issue that is not present in the tenant",
            )
        record: BeadsRecord = {
            "issue_id": issue_id,
            "text": body,
            "author": None,
            "created_at": None,
        }
        self._comments.setdefault(issue_id, []).append(record)

    def register_custom_statuses(self) -> None:
        """Record that custom-status registration ran."""
        self.custom_statuses_registered = True


_FAKE_HOLDER: list[FakeBeadsClient] = []


def _update_scalar_fields(*, record: BeadsRecord, fields: dict[str, Any]) -> None:
    """Apply every field the caller supplied, leaving the ones it did not alone.

    The fields ride as a mapping rather than as one parameter each because
    `update_issue` is a PARTIAL update: every column it can touch is an
    independent optional mutation, so a per-column parameter list grows with the
    schema and the body is the same two lines repeated once per column.
    """
    for key, value in fields.items():
        if value is not None:
            record[key] = value


def _update_assignee(
    *,
    record: BeadsRecord,
    assignee: str | None,
    clear_assignee: bool,
) -> None:
    if clear_assignee or assignee is not None:
        record["assignee"] = None if clear_assignee else assignee


def _add_labels(*, record: BeadsRecord, labels: list[str] | None) -> None:
    if labels is None:
        return
    existing = cast("list[str]", record.get("labels", []))
    merged = list(existing)
    for label in labels:
        if label not in merged:
            merged.append(label)
    record["labels"] = merged


def _remove_labels(*, record: BeadsRecord, labels: list[str] | None) -> None:
    if labels is None:
        return
    current = cast("list[str]", record.get("labels", []))
    record["labels"] = [label for label in current if label not in labels]


def _is_child_of(*, record: BeadsRecord, parent_id: str) -> bool:
    issue_id = record.get("id")
    return record.get("parent_id") == parent_id or (
        isinstance(issue_id, str) and issue_id.startswith(f"{parent_id}.")
    )


def fake_singleton() -> FakeBeadsClient:
    """Return the process-singleton fake tenant."""
    if not _FAKE_HOLDER:
        _FAKE_HOLDER.append(FakeBeadsClient())
    return _FAKE_HOLDER[0]


def reset_fake_singleton() -> None:
    """Drop the process-singleton fake tenant (test-isolation hook)."""
    _FAKE_HOLDER.clear()
