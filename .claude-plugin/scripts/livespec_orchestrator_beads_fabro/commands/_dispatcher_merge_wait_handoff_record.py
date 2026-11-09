"""The DURABLE ledger record of a handed-off merge wait.

The journal row is written by the engine at the moment of the handoff; the only
thing on the tenant that outlives the checkout's `tmp/` tree is a COMMENT, so the
v324 clause requires one that opens with `livespec-merge-wait-handed-off`.

WHAT THE RECORD MAY NOT CARRY. Names and figures only: every name in the body is
either one of our own literals or has passed `is_identifier_shaped`, whose byte
set excludes `{`, so a template opener cannot reach it from the input side. A name
that is not identifier-shaped (a check called `coverage (shard 1)`, say) is LEFT
OUT and COUNTED, as the clause requires. The opener detector still runs,
fail-closed, because `bd comments` offers neither an edit nor a delete verb and a
comment carrying an opener would cost the item every later dispatch.

EVERY FAILURE ARM IS JOURNALED AND NONE IS RAISED. The clause says a comment that
fails the detector, or that cannot be written, MUST NOT prevent the handoff.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    is_identifier_shaped,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    MERGE_WAIT_HANDED_OFF_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "MERGE_WAIT_HANDED_OFF_MARKER",
    "merge_wait_handed_off_comment_body",
    "record_merge_wait_handed_off",
]

MERGE_WAIT_HANDED_OFF_MARKER = "livespec-merge-wait-handed-off"

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_UNREPORTED = "(not reported by the forge view)"

_DECISION = (
    "decision: the merge wait's poll budget ended before the pull request's checks did, and "
    "no agent asked anything, so no answer is owed. The pull request is armed and the item "
    "stays active under its claim: the Dispatcher's next stranded-claim reconciliation pass "
    "accepts the item when the pull request merges, and rests it for a human only if a "
    "required check fails or the pull request closes unmerged. Do NOT close, rebase or "
    "disarm the pull request by hand, and run neither resolve-blocked nor resume."
)


def record_merge_wait_handed_off(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Append the durable comment for a handed-off merge wait, once.

    Returns without writing for any other outcome. The guard is the TYPED
    `merge_wait_handed_off` field rather than a match on the status string.
    """
    handed_off = outcome.merge_wait_handed_off
    if handed_off is None:
        return
    body = merge_wait_handed_off_comment_body(
        work_item_id=outcome.work_item_id,
        run_id=outcome.fabro_run_id,
        factory=handed_off.factory,
        pr_number=outcome.pr_number,
        pr_head=handed_off.pr_head,
        waited_seconds=handed_off.waited_seconds,
        running_checks=handed_off.running_checks,
    )
    findings = minijinja_openers_in_text(source=MERGE_WAIT_HANDED_OFF_MARKER, text=body)
    if findings:
        journal.append(
            record={
                "stage": f"{MERGE_WAIT_HANDED_OFF_STAGE}-refused",
                "work_item_id": item.id,
                "reason": f"template opener present: {', '.join(f.opener for f in findings)}",
            }
        )
        return
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=body,
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        journal.append(
            record={
                "stage": f"{MERGE_WAIT_HANDED_OFF_STAGE}-error",
                "work_item_id": item.id,
                "reason": type(written.error).__name__,
            }
        )
        return
    journal.append(
        record={
            "stage": f"{MERGE_WAIT_HANDED_OFF_STAGE}-record",
            "work_item_id": item.id,
            "pr_number": outcome.pr_number,
        }
    )


def merge_wait_handed_off_comment_body(  # noqa: PLR0913 — kw-only renderer; each field is an independent fact the clause names.
    *,
    work_item_id: str,
    run_id: str | None,
    factory: str,
    pr_number: int | None,
    pr_head: str | None,
    waited_seconds: int,
    running_checks: tuple[str, ...],
) -> str:
    """Render the handoff record. PURE, so each claim is testable in isolation.

    A scalar name is graded three ways, as the sibling records grade theirs: present
    and identifier-shaped is rendered, present but not identifier-shaped is left out
    and counted, and never reported by the forge is stated as unreported and NOT
    counted. Every running check is graded the first two ways.
    """
    rendered: list[str] = []
    left_out = 0
    for label, value in (("run id", run_id), ("factory", factory), ("pull request head", pr_head)):
        if value is None:
            rendered.append(f"{label}: {_UNREPORTED}")
        elif is_identifier_shaped(value=value):
            rendered.append(f"{label}: {value}")
        else:
            left_out += 1
    shaped = [name for name in running_checks if is_identifier_shaped(value=name)]
    left_out += len(running_checks) - len(shaped)
    lines = [
        MERGE_WAIT_HANDED_OFF_MARKER,
        "",
        f"work-item: {work_item_id}",
        f"pull request: {_UNREPORTED if pr_number is None else pr_number}",
        *rendered,
        f"seconds the merge wait spent: {waited_seconds}",
        f"required checks still running: {', '.join(shaped) if shaped else 'none'}",
        "",
        f"{left_out} names were left out for not being identifier-shaped.",
        "",
        _DECISION,
    ]
    return "\n".join(lines)
