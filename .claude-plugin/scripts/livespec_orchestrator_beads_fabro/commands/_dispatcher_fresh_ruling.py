"""Operator rulings that an item's next dispatch start fresh.

`dispatcher.py fresh-ruling` records the ruling as one append-only ledger
comment on the item, which is what recovery routing reads from any checkout,
and as one journal record, which is the host's own account of the act.

The comment is graded by the shared template-opener detector BEFORE it is
written, because a ledger comment cannot be edited or deleted afterwards and
one carrying a MiniJinja opener would poison every later goal render of the
item. A refusal exits 3 and writes neither the comment nor the record.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_findings_detail,
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
    invoker_from_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "FRESH_RULING_MARKER",
    "FRESH_RULING_STAGE",
    "add_fresh_ruling_arguments",
    "fresh_ruling_comment_body",
    "run_fresh_ruling_command",
]

FRESH_RULING_MARKER = "livespec-fresh-ruling"
FRESH_RULING_STAGE = "fresh-ruling"


def fresh_ruling_comment_body(*, work_item_id: str, invoker: str, reason: str, instant: str) -> str:
    """Render the stable ledger body a later recovery routing reads."""
    return "\n".join(
        (
            FRESH_RULING_MARKER,
            f"work-item: {work_item_id}",
            f"invoker: {invoker}",
            f"reason: {reason}",
            f"instant: {instant}",
        )
    )


def add_fresh_ruling_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the fresh-ruling flag surface to its subparser."""
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--reason", dest="reason", required=True)
    _ = parser.add_argument("--journal", dest="journal", default=None)


def run_fresh_ruling_command(*, args: argparse.Namespace) -> int:
    """Rule that the item's next dispatch starts fresh, on the ledger and the journal."""
    repo = Path(args.repo)
    identity = invoker_from_args(args=args)
    instant = utc_now_iso()
    reason = str(args.reason)
    body = fresh_ruling_comment_body(
        work_item_id=args.item, invoker=identity.invoker, reason=reason, instant=instant
    )
    findings = minijinja_openers_in_text(source=FRESH_RULING_MARKER, text=body)
    if findings:
        _ = write_stderr(
            text=f"ERROR: fresh-ruling refused: {minijinja_findings_detail(findings=findings)}\n"
        )
        return EXIT_PRECONDITION_ERROR
    append_work_item_comment(path=store_config(repo=repo), work_item_id=args.item, body=body)
    JournalFile(path=journal_path(args=args, repo=repo), identity=identity).append(
        record={
            "stage": FRESH_RULING_STAGE,
            "work_item_id": args.item,
            "reason": reason,
            "instant": instant,
        }
    )
    _ = write_stdout(text=f"FRESH-RULING  {args.item}  by {identity.invoker} at {instant}\n")
    return 0
