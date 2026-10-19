"""Export an orphaned run's record before anything terminates it.

The maintainer's 2026-08-26 ruling is that a dead factory run may be reaped
without a per-instance ask ONLY after its record has been captured into a
durable ledger comment AND that comment has been VERIFIED BY READ-BACK. This
module is that procedure made mechanical, so the reconciler inherits the
authorization rather than asking for it once per run.

The read-back is not ceremony. `bd show --json` carries no comments at all,
so the obvious verification reports a successful write as lost; the comment
bodies live under `bd comments <id> --json` and, within each record, under
`text` rather than `body`. Both traps are catalogued in this repo's agent
instructions, and both would turn a real export into an apparent failure —
which is why this module reads exactly that surface and that key.

A pointer ALREADY on the item for this run id is located rather than
rewritten. Ledger comments are append-only, so a reconciler that rewrote one
per pass would grow the record without adding anything to it.

One case has no ledger comment available: an orphan whose work-item is
absent from the ledger entirely. There is no issue to comment on, so the
pointer body comes back on the outcome and the caller writes it to the
dispatch journal, which is the only durable surface left. The export still
happens BEFORE the terminate in both worlds; only its destination differs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference import (
    pointer_record_for_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_check import (
    parse_preserved_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "ExportOutcome",
    "LedgerComments",
    "export_orphan_reference",
    "export_run_reference",
]

_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)
# The comment-body key. `body` and `content` both read as an empty string on
# every record, which is the same observation a lost write produces.
_COMMENT_TEXT_KEY = "text"
_UNREPORTED_COMMENT_ID = "(no comment id reported by bd comments)"


class LedgerComments(Protocol):
    """The ONLY ledger surface the reconciler is allowed to touch.

    Deliberately narrow: the reconciler must never write an item's status,
    `blocked_reason`, or labels — the decision stays in the ledger where a
    human owns it — so the seam it is handed cannot express those writes.
    """

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        """Return an issue's comments (`bd comments <id> --json`)."""
        ...

    def add_comment(self, *, issue_id: str, body: str) -> None:
        """Append one comment to an issue."""
        ...


@dataclass(frozen=True, kw_only=True)
class ExportOutcome:
    """Whether this run's record is durably preserved, and where.

    `journal_body` is non-None only for the no-such-item case, where the
    caller is the one holding the durable surface.
    """

    exported: bool
    comment_id: str | None
    journal_body: str | None
    detail: str


def export_orphan_reference(
    *,
    orphan: OrphanRun,
    repo: Path,
    fabro_bin: str,
    runner: CommandRunner,
    ledger: LedgerComments,
) -> ExportOutcome:
    """Preserve one orphan's record, verifying the write by read-back."""
    return export_run_reference(
        work_item_id=orphan.work_item_id,
        work_item_status=orphan.work_item_status,
        run_id=orphan.run_id,
        factory_server_url=orphan.factory_server_url,
        repo=repo,
        fabro_bin=fabro_bin,
        runner=runner,
        ledger=ledger,
    )


def export_run_reference(  # noqa: PLR0913 — kw-only export; the run's identity, its factory and the three seams are independent inputs.
    *,
    work_item_id: str,
    work_item_status: str | None,
    run_id: str,
    factory_server_url: str,
    repo: Path,
    fabro_bin: str,
    runner: CommandRunner,
    ledger: LedgerComments,
) -> ExportOutcome:
    """Preserve ONE run's record on its work-item, verifying it by read-back.

    PUBLIC and orphan-free because the whole-run wall budget takes the same
    export-then-terminate precondition for a run no reconciliation ever
    classified: its run is the dispatch's OWN, live, and about to be cancelled.
    A second copy of this procedure would write a pointer body one read-back
    could recognise and the other could not, which is the one property the
    module docstring above says the two paths must share.

    The ORPHAN-shaped entry point above is kept rather than retired because its
    caller holds an `OrphanRun` and nothing else: handing this the four fields
    it actually reads is what keeps a budget cancel from having to invent an
    orphan reason, a factory name and a status for a run that is none of those
    things.
    """
    pointer = attempt(
        action=lambda: pointer_record_for_run(
            fabro_bin=fabro_bin,
            repo=repo,
            item_id=work_item_id,
            run_id=run_id,
            server_url=factory_server_url,
            command_runner=runner,
        ),
        exceptions=(OSError,),
    )
    if isinstance(pointer, AttemptFailure):
        return ExportOutcome(
            exported=False,
            comment_id=None,
            journal_body=None,
            detail=f"fabro export failed with {type(pointer.error).__name__}: {pointer.error}",
        )
    if work_item_status is None:
        return ExportOutcome(
            exported=True,
            comment_id=None,
            journal_body=pointer.body,
            detail="work-item absent from the ledger; pointer preserved in the dispatch journal",
        )
    return _preserved_on_item(
        work_item_id=work_item_id, run_id=run_id, ledger=ledger, body=pointer.body
    )


def _preserved_on_item(
    *,
    work_item_id: str,
    run_id: str,
    ledger: LedgerComments,
    body: str,
) -> ExportOutcome:
    located = _pointer_comment_id(ledger=ledger, work_item_id=work_item_id, run_id=run_id)
    if isinstance(located, AttemptFailure):
        return _ledger_failure(error=located.error, verb="read")
    if located is not None:
        return ExportOutcome(
            exported=True,
            comment_id=located,
            journal_body=None,
            detail=f"located an existing preserve-by-reference comment for {run_id}",
        )
    written = attempt(
        action=lambda: ledger.add_comment(issue_id=work_item_id, body=body),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        return _ledger_failure(error=written.error, verb="write")
    return _read_back(work_item_id=work_item_id, run_id=run_id, ledger=ledger)


def _read_back(*, work_item_id: str, run_id: str, ledger: LedgerComments) -> ExportOutcome:
    confirmed = _pointer_comment_id(ledger=ledger, work_item_id=work_item_id, run_id=run_id)
    if isinstance(confirmed, AttemptFailure):
        return _ledger_failure(error=confirmed.error, verb="read back")
    if confirmed is None:
        return ExportOutcome(
            exported=False,
            comment_id=None,
            journal_body=None,
            detail=(
                f"the preserve-by-reference comment for {run_id} did not read back "
                f"from bd comments on {work_item_id}"
            ),
        )
    return ExportOutcome(
        exported=True,
        comment_id=confirmed,
        journal_body=None,
        detail=f"preserve-by-reference comment written and read back for {run_id}",
    )


def _ledger_failure(*, error: Exception, verb: str) -> ExportOutcome:
    return ExportOutcome(
        exported=False,
        comment_id=None,
        journal_body=None,
        detail=f"could not {verb} the preserve-by-reference comment: {type(error).__name__}",
    )


def _pointer_comment_id(
    *,
    ledger: LedgerComments,
    work_item_id: str,
    run_id: str,
) -> str | AttemptFailure | None:
    comments = attempt(
        action=lambda: ledger.list_comments(issue_id=work_item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return comments
    return _matching_comment_id(comments=comments, run_id=run_id)


def _matching_comment_id(*, comments: Sequence[Mapping[str, Any]], run_id: str) -> str | None:
    for comment in comments:
        text = comment.get(_COMMENT_TEXT_KEY)
        if not isinstance(text, str):
            continue
        pointer = parse_preserved_pointer(body=text)
        if pointer is not None and pointer.run_id == run_id:
            return _comment_id(comment=comment)
    return None


def _comment_id(*, comment: Mapping[str, Any]) -> str:
    """The comment's id, or an explicit mark that the record carried none.

    A MARK rather than None on purpose: None already means "no pointer for
    this run exists", and collapsing "found it, but bd reported no id" into
    that would report a preserved run as unpreserved and re-write the comment
    on every pass.
    """
    identifier: object = comment.get("id")
    if identifier is None:
        return _UNREPORTED_COMMENT_ID
    return str(identifier)
