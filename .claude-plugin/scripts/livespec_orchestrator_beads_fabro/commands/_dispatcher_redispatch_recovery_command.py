"""`dispatcher.py record-redispatch-recovery`: record a typed causal recovery attempt.

The across-dispatch progress gate refuses the next claim of an item whose recent
attempts stopped advancing, and only a fresh typed causal recovery attempt admits
one more epoch.  This is the sanctioned writer of that attempt: it appends the
record to the item's ledger comments, where every dispatching host reads it.  It
files NOTHING that could move the original required-result deadline -- the record
has no deadline field -- and it never dispatches; the gate grades the record
against the item's actual history at the next admission.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_recovery_record import (
    consumed_attempt_ids,
    parse_recovery_comments,
    render_recovery_comment,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "add_record_redispatch_recovery_arguments",
    "run_record_redispatch_recovery_command",
]

_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def add_record_redispatch_recovery_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Register the typed recovery attempt's fields as required arguments."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--attempt-id", dest="attempt_id", required=True)
    _ = parser.add_argument("--prior-run", dest="prior_runs", action="append", required=True)
    _ = parser.add_argument("--diagnosis", dest="diagnosis", required=True)
    _ = parser.add_argument("--operation", dest="operation", required=True)
    _ = parser.add_argument("--execution-evidence", dest="execution_evidence", required=True)


def run_record_redispatch_recovery_command(*, args: argparse.Namespace) -> int:
    """Append the recovery attempt, or name why it was refused (nothing is written)."""
    recovery = RedispatchRecovery(
        attempt_id=args.attempt_id.strip(),
        prior_run_ids=tuple(run.strip() for run in args.prior_runs),
        diagnosis=args.diagnosis.strip(),
        operation=args.operation.strip(),
        execution_evidence=args.execution_evidence.strip(),
    )
    refusal = _field_refusal(recovery=recovery)
    config = store_config(repo=Path(args.repo))
    if refusal is None:
        refusal = _reuse_refusal(config=config, item_id=args.item, recovery=recovery)
    if refusal is not None:
        _ = write_stderr(text=f"LIVESPEC_REDISPATCH_RECOVERY_REFUSED: {refusal}\n")
        return EXIT_PRECONDITION_ERROR
    append_work_item_comment(
        path=config, work_item_id=args.item, body=render_recovery_comment(recovery=recovery)
    )
    _ = write_stdout(text=f"recorded redispatch recovery attempt {recovery.attempt_id}\n")
    return 0


def _field_refusal(*, recovery: RedispatchRecovery) -> str | None:
    """A missing typed field, or text the goal brief could not carry."""
    fields = {
        "attempt id": recovery.attempt_id,
        "measured diagnosis": recovery.diagnosis,
        "executable operation": recovery.operation,
        "execution evidence": recovery.execution_evidence,
    }
    for name, value in fields.items():
        if value == "":
            return f"a typed causal recovery requires {name}"
        if minijinja_openers_in_text(source=name, text=value):
            return f"{name} carries a template opener a ledger comment cannot hold"
    if any(run == "" for run in recovery.prior_run_ids):
        return "a typed causal recovery requires non-empty prior run ids"
    return None


def _reuse_refusal(
    *, config: StoreConfig, item_id: str, recovery: RedispatchRecovery
) -> str | None:
    """A recovery attempt id is fresh exactly once; a reused one is refused."""
    comments = attempt(
        action=lambda: read_work_item_comments(path=config, work_item_id=item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return f"the ledger comments of {item_id} could not be read: {comments.error}"
    bodies = tuple(comment.text for comment in comments)
    recorded = {entry.attempt_id for entry in parse_recovery_comments(bodies=bodies)}
    if recovery.attempt_id in recorded | consumed_attempt_ids(bodies=bodies):
        return f"recovery attempt id {recovery.attempt_id} was already used; record a fresh one"
    return None
