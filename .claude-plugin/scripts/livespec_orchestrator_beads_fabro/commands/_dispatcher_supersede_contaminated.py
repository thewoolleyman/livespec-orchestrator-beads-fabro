"""The append-only escape hatch for a comment-contaminated work item."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_PARENT_CHILD,
    EDGE_SUPERSEDES,
    BeadsClient,
    BeadsRecord,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro._store_comments import (
    WorkItemComment,
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_findings_detail,
    minijinja_openers_in_item_fields,
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
    invoker_from_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path, store_config
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "add_supersede_contaminated_arguments",
    "copied_comment_body",
    "run_supersede_contaminated_command",
]

_STAGE = "supersede-contaminated"
_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def copied_comment_body(
    *, original_id: str, comment_id: str | None, created_at: str | None, text: str
) -> str:
    """Copy one rider with durable provenance and safe goal-template prose."""
    provenance = (
        f"Superseded from {original_id} comment {comment_id or 'unknown'} "
        f"created {created_at or 'unknown'}."
    )
    lines = text.splitlines()
    if lines and lines[0].startswith("FOR ") and lines[0].endswith(" ONLY:"):
        return "\n".join((lines[0], provenance, _sanitize(text="\n".join(lines[1:]))))
    return "\n".join((provenance, _sanitize(text=text)))


def add_supersede_contaminated_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the narrow operator surface for replacing one poisoned item."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--reason", dest="reason", required=True)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    add_invoker_argument(parser=parser)


def run_supersede_contaminated_command(*, args: argparse.Namespace) -> int:
    """File a safe successor, then record and close the unusable original."""
    repo = Path(args.repo)
    config = store_config(repo=repo)
    item = next((row for row in read_work_items(path=config) if row.id == args.item), None)
    if item is None:
        return _refuse(detail=f"work-item {args.item} is not in the tenant")
    if item.status == "done":
        return _refuse(detail=f"work-item {item.id} is closed")
    findings = minijinja_openers_in_item_fields(item=item)
    if findings:
        return _refuse(
            detail=(
                f"work-item {item.id} has editable field(s) to edit: "
                f"{minijinja_findings_detail(findings=findings)}"
            )
        )
    comments = read_work_item_comments(path=config, work_item_id=item.id)
    if not any(
        minijinja_openers_in_text(source="ledger comment", text=comment.text)
        for comment in comments
    ):
        return _refuse(detail=f"work-item {item.id} has no poisoned ledger comments")
    return _supersede(
        repo=repo, config=config, item=item, comments=comments, reason=str(args.reason), args=args
    )


def _supersede(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    comments: tuple[WorkItemComment, ...],
    reason: str,
    args: argparse.Namespace,
) -> int:
    """Perform post-filing work in order; never close the original on failure."""
    instant = utc_now_iso()
    client = make_beads_client(config=config)
    raw = client.show_issue(issue_id=item.id)
    successor = replace(
        item,
        id=new_work_item_id(prefix=config.prefix),
        status="backlog",
        assignee=None,
        captured_at=instant,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )
    filed = file_captured_work_item(
        path=config, item=successor, checklist=_CHECKLIST, plan_parent_id=_parent_id(record=raw)
    )
    if filed.__class__.__name__ != "IOSuccess":
        return _failed(successor_id=successor.id, step="capture filing")
    try:
        _copy_labels(client=client, raw=raw, successor_id=successor.id)
        record_ids = _copy_instruction_comments(
            client=client, original_id=item.id, successor_id=successor.id, comments=comments
        )
        _replace_inbound_blocks(client=client, original_id=item.id, successor_id=successor.id)
        client.add_dependency(from_id=successor.id, to_id=item.id, edge_type=EDGE_SUPERSEDES)
        _record_disposition_comments(
            original_id=item.id,
            successor_id=successor.id,
            reason=reason,
            record_ids=record_ids,
            config=config,
        )
        identity = invoker_from_args(args=args)
        JournalFile(path=journal_path(args=args, repo=repo), identity=identity).append(
            record={
                "stage": _STAGE,
                "original_id": item.id,
                "successor_id": successor.id,
                "reason": reason,
                "instant": instant,
            }
        )
        append_work_item(
            path=config,
            item=replace(
                item,
                status="done",
                resolution="duplicate",
                reason=reason,
                superseded_by=successor.id,
            ),
        )
    except (BeadsCommandError, BeadsConnectionError, BeadsMappingError, OSError) as error:
        return _failed(successor_id=successor.id, step=str(error))
    _ = write_stdout(text=f"SUPERSEDED {item.id} -> {successor.id}\n")
    return 0


def _sanitize(*, text: str) -> str:
    """Use the goal renderer's bracket form for every copied opener."""
    return text.replace("{{", "⟦⟦").replace("{%", "⟦%").replace("{#", "⟦#")


def _parent_id(*, record: BeadsRecord) -> str | None:
    """Return the parent-child target carried by the original, if any."""
    edges = record.get("dependencies")
    if isinstance(edges, list):
        for raw_edge in cast("list[object]", edges):
            edge = cast("BeadsRecord", raw_edge)
            target = edge.get("depends_on_id")
            if edge.get("type") == EDGE_PARENT_CHILD and isinstance(target, str):
                return target
    return None


def _copy_labels(*, client: BeadsClient, raw: BeadsRecord, successor_id: str) -> None:
    """Carry operator labels, excluding lifecycle, claim, and dispatch records."""
    labels = raw.get("labels")
    copied = (
        [
            raw_label
            for raw_label in cast("list[object]", labels)
            if isinstance(raw_label, str)
            and not raw_label.startswith(("lifecycle:", "claim:", "dispatch-record:"))
        ]
        if isinstance(labels, list)
        else []
    )
    if copied:
        client.update_issue(issue_id=successor_id, add_labels=copied)


def _copy_instruction_comments(
    *,
    client: BeadsClient,
    original_id: str,
    successor_id: str,
    comments: tuple[WorkItemComment, ...],
) -> tuple[str, ...]:
    """Copy riders in ledger order while leaving machine record comments behind."""
    record_ids: list[str] = []
    for comment in comments:
        if comment.text.startswith("livespec-"):
            if comment.comment_id is not None:
                record_ids.append(comment.comment_id)
            continue
        client.add_comment(
            issue_id=successor_id,
            body=copied_comment_body(
                original_id=original_id,
                comment_id=comment.comment_id,
                created_at=comment.created_at,
                text=comment.text,
            ),
        )
    return tuple(record_ids)


def _replace_inbound_blocks(*, client: BeadsClient, original_id: str, successor_id: str) -> None:
    """Move every consumer's blocks edge from original to successor."""
    for record in client.list_issues():
        from_id, edges = record.get("id"), record.get("dependencies")
        if (
            isinstance(from_id, str)
            and isinstance(edges, list)
            and _blocks(record_edges=cast("list[object]", edges), original_id=original_id)
        ):
            client.remove_dependency(from_id=from_id, to_id=original_id)
            client.add_dependency(from_id=from_id, to_id=successor_id, edge_type=EDGE_BLOCKS)


def _blocks(*, record_edges: list[object], original_id: str) -> bool:
    """Whether one raw issue row is blocked on the contaminated original."""
    return any(
        cast("BeadsRecord", raw_edge).get("type") == EDGE_BLOCKS
        and cast("BeadsRecord", raw_edge).get("depends_on_id") == original_id
        for raw_edge in record_edges
    )


def _record_disposition_comments(
    *,
    original_id: str,
    successor_id: str,
    reason: str,
    record_ids: tuple[str, ...],
    config: StoreConfig,
) -> None:
    """Write reciprocal disposition accounts before the original is closed."""
    ids = ", ".join(record_ids) or "none"
    append_work_item_comment(
        path=config,
        work_item_id=successor_id,
        body=(
            f"Supersedes {original_id}; reason: {reason}; "
            f"record comments left on original: {ids}."
        ),
    )
    append_work_item_comment(
        path=config,
        work_item_id=original_id,
        body=f"Superseded by {successor_id}; reason: {reason}.",
    )


def _refuse(*, detail: str) -> int:
    _ = write_stderr(text=f"ERROR: supersede-contaminated refused: {detail}\n")
    return EXIT_PRECONDITION_ERROR


def _failed(*, successor_id: str, step: str) -> int:
    _ = write_stderr(
        text=f"ERROR: supersede-contaminated successor {successor_id} failed at {step}\n"
    )
    return EXIT_FAILURE
