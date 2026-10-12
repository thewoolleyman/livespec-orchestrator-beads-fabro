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

# The id shape the server hands a no-history record. The live tenant mints
# `bd-ib-wisp-<hex>`; the fake counts instead, because a deterministic id is
# what lets a test name a token in an assertion. What matters is that the
# caller cannot CHOOSE it: a token id derived from any caller-supplied value
# would be an explicit-id create, which is an upsert and never an exclusion
# (relay research note 007).
_NO_HISTORY_ID_PREFIX = "fake-wisp-"

# The status the lifecycle guard forces onto every create, no-history records
# included (measured in relay research note 005).
_FORCED_CREATE_STATUS = "backlog"


class FakeBeadsClient:
    """Pure in-memory `BeadsClient` — runtime fallback + hermetic test backend.

    Holds a dict of issue records keyed by id. Each record is the same
    shape a parsed `bd ... --json` issue object has, so the store layer's
    field map works identically against the fake and the shell backend.
    Writes mutate the in-memory dict; reads return copies so callers
    cannot accidentally mutate the backing store.

    THREE OF ITS BEHAVIOURS ARE DELIBERATELY AWKWARD, because the server's
    are, and a convenient fake would make the epoch-token chain's exclusion
    untestable (relay research notes 005 and 007). `close_issue` is
    CONDITIONAL: a record already closed keeps its first close reason, as
    `bd close`'s `WHERE status != 'closed'` guarantees. `create_issue` with an
    id that already exists is an UPSERT that reopens the record and erases its
    close reason, which is why nothing may ever re-create a token id. And a
    no-history record is omitted from `list_issues` (and therefore from
    `exists`, which the shell client resolves through that same listing) while
    `show_issue` still returns it.
    """

    def __init__(self) -> None:
        self._issues: dict[str, BeadsRecord] = {}
        self._comments: dict[str, list[BeadsRecord]] = {}
        self._no_history: set[str] = set()
        self._assigned_ids: int = 0
        self.custom_statuses_registered: bool = False

    def list_issues(self) -> list[BeadsRecord]:
        return [
            dict(record)
            for issue_id, record in self._issues.items()
            if issue_id not in self._no_history
        ]

    def no_history_issue_ids(self) -> tuple[str, ...]:
        """Return the live no-history record ids (fake-only inspection seam).

        No list surface can answer this on the real server, which is the whole
        point of a no-history record; a test asserting how many token records
        stay live needs SOME way to count them, so the fake supplies one.
        """
        return tuple(sorted(self._no_history))

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
        """Report presence as the LIST surface sees it, no-history records aside.

        The shell client answers this from `list_issues`, which omits every
        no-history record, so a fake answering from its backing dict would
        report `True` where the live tenant reports `False`.
        """
        return issue_id in self._issues and issue_id not in self._no_history

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
        self._no_history.discard(draft.issue_id)
        return draft.issue_id

    def create_no_history_issue(self, *, title: str, description: str) -> str:
        """Create a no-history record under a SERVER-assigned id; return that id."""
        self._assigned_ids += 1
        issue_id = f"{_NO_HISTORY_ID_PREFIX}{self._assigned_ids}"
        self._issues[issue_id] = {
            "id": issue_id,
            "issue_type": "task",
            "title": title,
            "description": description,
            "priority": 2,
            "assignee": None,
            "created_at": None,
            "status": _FORCED_CREATE_STATUS,
            "close_reason": None,
            "labels": [],
            "metadata": {},
            "spec_id": None,
            "parent_id": None,
            "dependencies": [],
        }
        self._no_history.add(issue_id)
        return issue_id

    def delete_issue(self, *, issue_id: str) -> None:
        """Delete one record and its comments (`bd delete <id> --force`)."""
        if issue_id not in self._issues:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot delete an issue that is not present in the tenant",
            )
        del self._issues[issue_id]
        _ = self._comments.pop(issue_id, None)
        self._no_history.discard(issue_id)

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
        """Close one record CONDITIONALLY, as the server's own statement does.

        `bd close` is `UPDATE … SET status='closed', close_reason=? WHERE id=?
        AND status!='closed'`, so a second closer matches zero rows: the first
        reason stands and the second is discarded. Measured over 20 trials of
        4 concurrent closers in relay research note 005, where exactly one
        reason won every time.
        """
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot close an issue that is not present in the tenant",
            )
        if record.get("status") == "closed":
            return
        record["status"] = "closed"
        record["close_reason"] = reason

    def close_issue_without_verdict(self, *, issue_id: str, reason: str) -> None:
        """Attempt the conditional close, reporting NOTHING about who won.

        The real `bd` exit code does not identify the winner — a loser exits 0
        when its update matched no row, or exits 1 with Dolt `Error 1213` — so
        every caller must read `close_reason` back. This verb exists to make
        that unavoidable: it has no return value to misread.
        """
        self.close_issue(issue_id=issue_id, reason=reason)

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
