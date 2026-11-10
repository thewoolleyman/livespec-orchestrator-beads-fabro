"""Holds the dispatch journal alone records, composed as `hygiene:journal-hold:<subject>`.

Eleven hold or deferral stages write their state ONLY to this repository's
dispatch journal. Such a hold parks an item in exactly the shape every other
lane here ignores: the item rests in `ready` with no claim and no blocked reason,
so nothing is stranded, nothing ages past a bound, and the idle-factory fact
would count it dispatchable. The ratified "Journal-recorded holds" clause in
`SPECIFICATION/contracts.md` is the counterweight, and this module is its one
reader. The fold that decides which record is a subject's current hold lives in
`_needs_attention_journal_hold_fold`; this module owns the read and the facts.

Three properties are load-bearing rather than incidental.

THE FACTS ARE FOLDED FROM ONE READING OF THE JOURNAL. `read_journal_holds` reads
the journal once and returns everything the snapshot needs from it: the current
holds the facts are built from, and the set of items carrying a live
`recovery-held`, which the idle lanes subtract from admission eligibility. A
caller composing a whole snapshot takes one reading and hands it to every
consumer, so no two lanes can disagree about what the journal held.

AN UNREADABLE JOURNAL IS UNOBSERVABLE, NEVER EMPTY. An absent journal is a
repository that never dispatched and holds nothing; a journal that exists and
cannot be opened is a reading nobody took, and reporting it as "no holds" is the
one answer that would let a held item read as idle. The reading carries that
distinction so the idle lanes can refuse to assert idleness on it.

THE JOURNAL IS THE ONLY SOURCE. A launcher participates by appending a
`launcher-hold` record; its hold files, tickets and output are never read here.
Nothing in this module writes or reaches a factory, and the only clock it reads
is the one the seven-day age test needs, so two invocations over an unchanged
journal render byte-identical rows.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify import (
    CLOSED_STATUSES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_journal_hold_fold import (
    JournalHold,
    fold_journal_holds,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    dispatch_journal_path_for,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "JOURNAL_HOLD_FACT_PREFIX",
    "UNOBSERVABLE_SUBJECT",
    "JournalHoldReading",
    "journal_hold_items",
    "read_journal_holds",
]

JOURNAL_HOLD_FACT_PREFIX = "hygiene:journal-hold"
UNOBSERVABLE_SUBJECT = "unobservable"

_WORK_ITEM_KEY = "work_item_id"
_JOURNAL_SOURCE_PATH = "tmp/fabro-dispatch-journal.jsonl"

# A held item is invisible to every other lane, so the fact rides in the `high`
# band the idle-factory row it corrects occupies.
_URGENCY = "high"


@dataclass(frozen=True, kw_only=True)
class JournalHoldReading:
    """What one reading of the journal established.

    `observable` is False exactly when the journal exists and could not be read;
    `holds` is then empty and means "nobody looked", not "nothing is held".
    `live_recovery_held_ids` is the set the idle lanes subtract from admission
    eligibility: items whose newest `recovery-held` is within the window, not
    retired, and not closed — whichever record fills their fact.
    """

    observable: bool
    holds: tuple[JournalHold, ...]
    live_recovery_held_ids: frozenset[str]


def read_journal_holds(
    *,
    journal_path: Path,
    items: Sequence[WorkItem],
    now: datetime | None = None,
) -> JournalHoldReading:
    """Read the journal once into each subject's current hold."""
    opened = attempt(action=lambda: _open_and_close(path=journal_path), exceptions=(OSError,))
    if isinstance(opened, AttemptFailure):
        # An absent journal is a repository that never dispatched; any other
        # failure to open one that exists is a reading nobody took.
        return JournalHoldReading(
            observable=isinstance(opened.error, FileNotFoundError),
            holds=(),
            live_recovery_held_ids=frozenset(),
        )
    folded = fold_journal_holds(
        records=journal_tail_records(journal_path=journal_path),
        closed={item.id for item in items if item.status in CLOSED_STATUSES},
        now=datetime.now(timezone.utc) if now is None else now,
    )
    return JournalHoldReading(
        observable=True,
        holds=folded.holds,
        live_recovery_held_ids=folded.live_recovery_held_ids,
    )


def journal_hold_items(
    *,
    project_root: Path,
    repo: str,
    items: Sequence[WorkItem],
    reading: JournalHoldReading | None = None,
) -> list[AttentionItem]:
    """One fact per current hold, or the single unobservable fact when unreadable."""
    journal = dispatch_journal_path_for(project_root=project_root)
    resolved = (
        reading if reading is not None else read_journal_holds(journal_path=journal, items=items)
    )
    context = ConformanceContext(project_root=project_root, repo=repo)
    if not resolved.observable:
        return [
            context.candidate(
                id=f"{JOURNAL_HOLD_FACT_PREFIX}:{UNOBSERVABLE_SUBJECT}",
                kind="hygiene",
                urgency=_URGENCY,
                summary=(
                    f"The dispatch journal of {repo} cannot be read, so no journal-recorded "
                    f"hold can be reported for it and none may be assumed absent. "
                    f"Inspect {_JOURNAL_SOURCE_PATH}."
                ),
                source_ref=SourceRef(repo=repo, path=_JOURNAL_SOURCE_PATH),
                handoff=Handoff(kind="shell", command=f"ls -ld {shlex.quote(str(journal))}"),
            )
        ]
    return [
        context.candidate(
            id=f"{JOURNAL_HOLD_FACT_PREFIX}:{hold.subject}",
            kind="hygiene",
            urgency=_URGENCY,
            summary=_summary(hold=hold),
            source_ref=SourceRef(
                repo=repo,
                work_item=hold.subject if hold.subject_key == _WORK_ITEM_KEY else None,
                path=_JOURNAL_SOURCE_PATH,
            ),
            handoff=Handoff(kind="shell", command=_inspect_command(journal=journal, hold=hold)),
        )
        for hold in resolved.holds
    ]


def _open_and_close(*, path: Path) -> None:
    with path.open("rb"):
        pass


def _summary(*, hold: JournalHold) -> str:
    """Name the subject, the stage and every recorded reason key, from stored fields alone."""
    reasons = "".join(f"; {key}={value}" for key, value in hold.reasons)
    return (
        f"Dispatch journal records {hold.stage} for {hold.subject} (appended "
        f"{hold.appended_at}){reasons}. It stays until a later journal record retires "
        f"it or seven days pass. Inspect the recorded stage in the dispatch journal."
    )


def _inspect_command(*, journal: Path, hold: JournalHold) -> str:
    stage_field = shlex.quote(json.dumps({"stage": hold.stage})[1:-1])
    subject_field = shlex.quote(json.dumps({hold.subject_key: hold.subject})[1:-1])
    return f"grep -F {stage_field} {shlex.quote(str(journal))} | grep -F {subject_field}"
