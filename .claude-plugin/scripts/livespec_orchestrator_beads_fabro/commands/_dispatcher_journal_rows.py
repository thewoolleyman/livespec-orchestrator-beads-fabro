"""Reading this dispatch's own journal back, for the dispositions that need it.

Extracted VERBATIM from `_dispatcher_stall_disposition` when the whole-run wall
budget's disposition became the second reader of the same file. That module owns
WHICH rows a stall cancellation routes on and what the count means; this owns the
mechanics both dispositions share -- parse the file, keep the mappings in append
order, and recognise one stage written for one item.

WHY A DISPOSITION READS THE JOURNAL AT ALL. The cancel site read the run's own
record while the run still existed, which is the one moment it is readable; by
the time a disposition runs the run has been `fabro rm -f`-ed, so re-probing
would answer about nothing and would still succeed. Reading the row the cancel
wrote is therefore not a shortcut -- it is the only honest source, and it also
keeps the comment and the journal from describing one cancellation two ways.

EVERY READ FAILURE YIELDS THE EMPTY TUPLE rather than raising. The terminal is
already final, so a disposition that crashed on an unreadable journal would
strand the item it was about to dispose of; an empty tuple is read as "no row
was found", which each caller's comment states as such. A record that is not a
mapping is dropped for the same reason -- one malformed line must not cost an
item its rest state.

APPEND ORDER IS LOAD-BEARING and is why this returns a tuple rather than a set:
the stall arm counts cancellations in cancellation order, the budget arm reports
the NEWEST cancellation, and the stall replay asks what the journal recorded
AFTER a particular row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "journal_records",
    "names_stage",
]


def journal_records(*, journal: JournalFile) -> tuple[Mapping[str, object], ...]:
    """Every mapping record the journal file holds, in append order."""
    read = attempt(action=lambda: journal.path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return ()
    parsed = attempt(
        action=lambda: [json.loads(line) for line in read.splitlines()], exceptions=(ValueError,)
    )
    if isinstance(parsed, AttemptFailure):
        return ()
    records = cast("list[object]", parsed)
    return tuple(
        cast("Mapping[str, object]", record) for record in records if isinstance(record, dict)
    )


def names_stage(*, record: Mapping[str, object], item_id: str, stage: str) -> bool:
    """Whether this record is the named stage, written for the named item."""
    return record.get("stage") == stage and record.get("work_item_id") == item_id
