"""The append-only recovery command for a comment-contaminated work item."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import EDGE_SUPERSEDES, make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_comments import (
    copy_instruction_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_mutations import (
    copy_labels,
    parent_id,
    record_disposition_comments,
    replace_inbound_blocks,
)
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
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord
    from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "add_supersede_contaminated_arguments",
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


@dataclass(frozen=True, kw_only=True)
class Supersession:
    """The filed successor and the original facts needed to finish its disposition."""

    args: argparse.Namespace
    client: BeadsClient
    config: StoreConfig
    instant: str
    item: WorkItem
    raw: BeadsRecord
    reason: str
    successor: WorkItem


def add_supersede_contaminated_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the narrow operator surface for replacing one poisoned item."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--reason", dest="reason", required=True)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    add_invoker_argument(parser=parser)


def run_supersede_contaminated_command(*, args: argparse.Namespace) -> int:
    """File a successor before making any irreversible disposition writes."""
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
    poisoned = any(
        minijinja_openers_in_text(source="ledger comment", text=row.text) for row in comments
    )
    if not poisoned:
        return _refuse(detail=f"work-item {item.id} has no poisoned ledger comments")
    return _supersede(
        config=config,
        item=item,
        comments=comments,
        reason=str(args.reason),
        args=args,
    )


def _supersede(
    *,
    config: StoreConfig,
    item: WorkItem,
    comments: tuple[WorkItemComment, ...],
    reason: str,
    args: argparse.Namespace,
) -> int:
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
        path=config,
        item=successor,
        checklist=_CHECKLIST,
        plan_parent_id=parent_id(record=raw),
    )
    if filed.__class__.__name__ != "IOSuccess":
        return _failed(successor_id=successor.id, step="capture filing")
    state = Supersession(
        args=args,
        client=client,
        config=config,
        instant=instant,
        item=item,
        raw=raw,
        reason=reason,
        successor=successor,
    )
    return _finish(
        comments=comments,
        state=state,
    )


def _finish(
    *,
    comments: tuple[WorkItemComment, ...],
    state: Supersession,
) -> int:
    step = "copy labels"
    try:
        _copy_labels(client=state.client, raw=state.raw, successor_id=state.successor.id)
        step = "copy instruction comments"
        record_ids = copy_instruction_comments(
            client=state.client,
            original_id=state.item.id,
            successor_id=state.successor.id,
            comments=comments,
        )
        step = "replace inbound blocks"
        replace_inbound_blocks(
            client=state.client,
            original_id=state.item.id,
            successor_id=state.successor.id,
        )
        step = "write supersedes edge"
        state.client.add_dependency(
            from_id=state.successor.id,
            to_id=state.item.id,
            edge_type=EDGE_SUPERSEDES,
        )
        step = "write disposition comments"
        record_disposition_comments(
            original_id=state.item.id,
            successor_id=state.successor.id,
            reason=state.reason,
            record_ids=record_ids,
            config=state.config,
        )
        step = "write journal"
        JournalFile(
            path=journal_path(args=state.args, repo=Path(state.args.repo)),
            identity=invoker_from_args(args=state.args),
        ).append(
            record={
                "stage": _STAGE,
                "original_id": state.item.id,
                "successor_id": state.successor.id,
                "reason": state.reason,
                "instant": state.instant,
            }
        )
        step = "close original"
        append_work_item(
            path=state.config,
            item=replace(
                state.item,
                status="done",
                resolution="duplicate",
                reason=state.reason,
                superseded_by=state.successor.id,
            ),
        )
    except (BeadsCommandError, BeadsConnectionError, BeadsMappingError, OSError, ValueError):
        return _failed(successor_id=state.successor.id, step=step)
    _ = write_stdout(text=f"SUPERSEDED {state.item.id} -> {state.successor.id}\n")
    return 0


def _copy_labels(*, client: BeadsClient, raw: BeadsRecord, successor_id: str) -> None:
    """Keep the failure seam local while the mutation policy stays cohesive."""
    copy_labels(client=client, raw=raw, successor_id=successor_id)


def _refuse(*, detail: str) -> int:
    _ = write_stderr(text=f"ERROR: supersede-contaminated refused: {detail}\n")
    return EXIT_PRECONDITION_ERROR


def _failed(*, successor_id: str, step: str) -> int:
    _ = write_stderr(
        text=f"ERROR: supersede-contaminated successor {successor_id} failed at {step}\n"
    )
    return EXIT_FAILURE
