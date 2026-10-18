"""Writing each of a recovery's durable effects EXACTLY ONCE across replays.

A recovery writes three effects in a fixed order and can be killed between any
two of them — a provider-limit kill, a `fabro rm --force`, a Docker restart, a
dead drive process. The claim re-read stops a replay of a COMPLETED recovery,
because the row is no longer `active` and grades `claim-changed`. It cannot
stop a replay of an INTERRUPTED one: the row is still `active`, still assigned
`fabro`, still stamped with the same run — which is correct, since the
transition genuinely has not happened — so the replay runs again and, without
these readings, re-writes the two records that already exist.

THE LEDGER COMMENT IS THE EFFECT THAT CANNOT BE UNDONE. `bd comments` offers
neither edit nor delete, so a duplicate is permanent and an item accumulates
one per interrupted pass. The journal row matters for a different reason: the
repeat arm reads the predecessor's segment for a release row
(`observe_predecessor_history`), so a duplicated row is not merely noise — it
is evidence about a dispatch that did not produce it.

THE COMMENT IS MATCHED BY ITS WHOLE RENDERED BODY, not by its marker. The
marker alone recurs across every release of the same item, so a marker match
would read a PREVIOUS run's release as this one's and skip a comment that was
never written. The body names this run, this factory and this reason, and it is
rendered deterministically from the request — so comparing it entire is both
exact and free of a parse that could drift from the renderer.

AN UNREADABLE SOURCE IS `None`, NEVER `False`. This is the direction that
matters: `False` means "the effect is absent, write it", so a failure to read
the journal or the comments would present as permission to write a second
copy — the exact outcome these readings exist to prevent. The caller grades
`None` as `effect-unobservable` and writes nothing, and the next pass reads
again.

THE READ AND THE WRITE ARE PAIRED HERE, not at the caller, because a caller
holding the reading is a caller that can forget to consult it — and the
failure would be invisible, since writing an effect that already exists
succeeds. `establish_journal_record` and `establish_comment` therefore answer
WHAT HAPPENED (`EFFECT_WRITTEN`, `EFFECT_ALREADY_PRESENT`, or `None` for
unobservable) rather than handing back a predicate. The ORDER between the two
stays with the recovery, which is the module that owns the clause's sequence;
this owns only the once-ness of each.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects import (
    append_claim_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    journal_records_or_none,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "EFFECT_ALREADY_PRESENT",
    "EFFECT_WRITTEN",
    "comment_already_written",
    "establish_comment",
    "establish_journal_record",
    "journal_record_already_written",
]

# What one `establish_*` call did. Two NAMED answers rather than a boolean,
# because the caller reports the effects it performed and "written" versus
# "already there" is exactly that distinction — a boolean at this seam reads as
# success/failure, which is a third thing neither value means.
EFFECT_WRITTEN = "written"
EFFECT_ALREADY_PRESENT = "already-present"

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
_RUN_ID_KEY = "run_id"

_LEDGER_READ_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def journal_record_already_written(
    *,
    journal_path: Path,
    stage: str,
    work_item_id: str,
    run_id: str,
) -> bool | None:
    """Whether this journal already carries THIS recovery's row.

    Keyed on all three of stage, item and run. The stage alone would match the
    other route's row, and the stage with the item alone would match a release
    of an EARLIER run of the same item — which is a row this item legitimately
    carries and which says nothing about the run being recovered now.
    """
    records = journal_records_or_none(journal_path=journal_path)
    if records is None:
        return None
    return any(
        record.get(_STAGE_KEY) == stage
        and record.get(_WORK_ITEM_KEY) == work_item_id
        and record.get(_RUN_ID_KEY) == run_id
        for record in records
    )


def comment_already_written(*, repo: Path, work_item_id: str, body: str) -> bool | None:
    """Whether this item already carries the exact comment this recovery renders.

    Compared on the stripped text so a transport that trims trailing newlines
    does not report an identical comment as absent — which would write the one
    duplicate that can never be removed.
    """
    comments = attempt(
        action=lambda: read_work_item_comments(
            path=store_config(repo=repo), work_item_id=work_item_id
        ),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return None
    wanted = body.strip()
    return any(comment.text.strip() == wanted for comment in comments)


def establish_journal_record(
    *,
    journal: JournalFile,
    stage: str,
    work_item_id: str,
    run_id: str,
    record: dict[str, object],
) -> str | None:
    """Append this recovery's journal row unless it is already there."""
    already = journal_record_already_written(
        journal_path=journal.path, stage=stage, work_item_id=work_item_id, run_id=run_id
    )
    if already is None:
        return None
    if already:
        return EFFECT_ALREADY_PRESENT
    journal.append(record=record)
    return EFFECT_WRITTEN


def establish_comment(*, repo: Path, work_item_id: str, body: str) -> str | None:
    """Append this recovery's ledger comment unless it is already there.

    The one effect that can never be undone, so BOTH the read that guards it
    and the write itself answer `None` on failure: an unreadable comment list
    must not read as an absent comment, and a refused append must not read as
    one that landed.
    """
    already = comment_already_written(repo=repo, work_item_id=work_item_id, body=body)
    if already is None:
        return None
    if already:
        return EFFECT_ALREADY_PRESENT
    if not append_claim_comment(repo=repo, work_item_id=work_item_id, body=body):
        return None
    return EFFECT_WRITTEN
