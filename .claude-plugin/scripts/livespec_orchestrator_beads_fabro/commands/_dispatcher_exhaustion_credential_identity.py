"""WHICH CREDENTIAL ACCOUNT a provider-exhaustion record speaks for.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" -> "Every observed availability record is scoped,
versioned, and expires": a provider-exhaustion record "MUST also carry the
opaque non-secret credential identity that the dispatch's admission
session-headroom assessment journaled ... when that assessment journaled one".

WHY THE VENDOR LABEL WAS NOT ENOUGH, which is the measurement this module
exists for. The account the factory spends is swapped BEHIND one vendor by a
selection process outside the Dispatcher, so a record labelled only `anthropic`
cannot tell an exhausted account from a fresh one. Measured 2026-10-16: the
selection rotated from `anthropic-1` to `anthropic-3` at 16:52Z, four in-flight
`anthropic-1` runs met the session limit between 17:35Z and 17:41Z, and the
records their closes minted refused every `anthropic-3` dispatch until
17:50:19Z. Every one of those refusals was correct about the vendor and wrong
about the allowance, and nothing in the record said which.

THE IDENTITY IS THE ADMISSION'S, NOT A FRESH READING. The label is taken from
what the session-headroom assessment ALREADY JOURNALED for the dispatch, never
from a second probe of the environment: the record must name the account whose
ceiling the run actually met, and by the time the mint runs the dispatch has
finished and the selection may already have moved on. A re-read there would
label the record with whichever account is current, which is the exact
confusion being retired.

EVERY UNREADABLE LINE AND EVERY ILL-SHAPED RECORD IS PASSED OVER, exactly as
`_dispatcher_session_headroom_baseline` passes them over and for the same
reason: the journal is append-only and written by concurrent passes, so a
truncated last line is an ordinary state rather than a fault, and raising from
here would fail a terminal disposition over a label the mint can honestly omit.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    ABSENT_CREDENTIAL_IDENTITY,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "journaled_admission_credential_identity",
]


def journaled_admission_credential_identity(
    *, journal_path: Path | None, work_item_id: str
) -> str | None:
    """The credential identity this item's NEWEST admission assessment named.

    NEWEST, and only the newest: one admission evaluation journals one record
    per affected work-item, and an item re-evaluated across passes carries one
    record per pass. The dispatch that observed the ceiling was admitted by the
    last of them, so an older record names an account that evaluation had
    already moved off -- which is the same stale label this module exists to
    stop writing.

    `None` says the assessment journaled NO identity, which the clause treats
    as a record that carries none rather than as a fault. Three different
    states reach it and all three owe the same answer: no assessment was
    journaled for this item (an evaluation that assessed no covered candidate,
    or a journal this build cannot see), the newest one carried only
    unobservable readings, or the projected credential was ABSENT -- and "An
    absent identity is not a credential identity" is the clause's own wording.
    """
    if journal_path is None or not journal_path.is_file():
        return None
    for line in reversed(journal_path.read_text(encoding="utf-8").splitlines()):
        record = _record(line=line)
        if record is None or record.get("stage") != SESSION_HEADROOM_STAGE:
            continue
        if record.get("work_item_id") != work_item_id:
            continue
        return _named_identity(assessments=record.get("assessments"))
    return None


def _named_identity(*, assessments: object) -> str | None:
    """The first real credential identity one assessment record's readings name.

    FIRST rather than every, because the clause asks the record to name "the
    opaque non-secret credential identity that the dispatch's admission
    session-headroom assessment journaled" -- one label on one record. The
    readings are deduplicated by identity before they are journaled, and a
    dispatch assessing two accounts at once is a shape no committed chain in
    this fleet renders; naming the first keeps the record single-valued instead
    of inventing a set the clause has no coverage rule for.
    """
    if not isinstance(assessments, list):
        return None
    for entry in cast("list[object]", assessments):
        if not isinstance(entry, dict):
            continue
        identity = cast("dict[object, object]", entry).get("credential_identity")
        if isinstance(identity, str) and identity != ABSENT_CREDENTIAL_IDENTITY:
            return identity
    return None


def _record(*, line: str) -> dict[str, object] | None:
    parsed = parse_json(text=line)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    mapping = cast("dict[object, object]", parsed)
    return {str(key): value for key, value in mapping.items()}
