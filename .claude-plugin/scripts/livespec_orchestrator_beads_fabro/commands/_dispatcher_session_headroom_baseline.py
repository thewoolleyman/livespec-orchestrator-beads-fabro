"""Reading this repository's dispatch journal for one credential's earlier readings.

Work-item `bd-ib-rszkjc`: the drain rate's baseline is "the earliest valid
assessment of the same credential identity in the same repository's dispatch
journal, for any work-item", observed inside the clause's age window. This
module supplies the candidates; `_acp_session_headroom_drain` decides which of
them is the baseline and what the rate is, so the whole decision stays
exercisable without a journal on disk.

THE HISTORY IS THE JOURNAL THE DISPATCH IS ACTUALLY WRITING, which is why the
path is PASSED IN rather than derived from the repository root. `dispatcher.py`
accepts a `--journal` override, so a path re-derived here would read a
different file from the one this pass appends to -- a clean, plausible "no
baseline held" for a journal full of them, which is the wrong-population
reading the fleet trap catalogue describes.

FOR ANY WORK-ITEM, DELIBERATELY. The journal writes one assessment record per
affected work-item per admission evaluation, all carrying the same reading, and
the quantity being measured belongs to the CREDENTIAL rather than to any item.
Scoping the history to one item would make the rate unmeasurable for the first
dispatch of every item while an hour of readings for that same credential sat
in the file.

THE IDENTITY MATCH IS WHAT MAKES THE RATE MEAN ANYTHING. Each pool slot drains
independently and `_dispatcher_factory_account_selector` can name a different
one between passes, so a baseline from another credential subtracts one
account's utilization from another's and reports the difference as a rate. The
identities are opaque digests, so the comparison is exact equality and nothing
about spelling.

EVERY UNREADABLE LINE AND EVERY ILL-SHAPED RECORD IS PASSED OVER. The journal
is append-only and is written by concurrent passes, so a truncated last line is
an ordinary state rather than a fault -- and this read decides nothing: the
worst outcome of skipping a line is a null drain rate, while raising from here
would fail an admission evaluation over a journal-only figure.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    baseline_assessment,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "session_headroom_baseline",
]


def session_headroom_baseline(
    *, journal_path: Path | None, credential_identity: str, now_iso: str
) -> SessionHeadroomBaseline | None:
    """This credential's baseline reading from this repository's dispatch journal.

    An absent or not-yet-written journal is `None` rather than an error: the
    first dispatch in a fresh clone has no history, and that is the same answer
    a journal carrying nothing in the window gives.
    """
    if journal_path is None or not journal_path.is_file():
        return None
    return baseline_assessment(
        candidates=_candidates(
            text=journal_path.read_text(encoding="utf-8"),
            credential_identity=credential_identity,
        ),
        now_iso=now_iso,
    )


def _candidates(*, text: str, credential_identity: str) -> tuple[SessionHeadroomBaseline, ...]:
    """Every valid earlier assessment of ONE credential, in journal order."""
    candidates: list[SessionHeadroomBaseline] = []
    for line in text.splitlines():
        record = _record(line=line)
        if record is None or record.get("stage") != SESSION_HEADROOM_STAGE:
            continue
        assessments = record.get("assessments")
        if not isinstance(assessments, list):
            continue
        for entry in cast("list[object]", assessments):
            candidate = _candidate(entry=entry, credential_identity=credential_identity)
            if candidate is not None:
                candidates.append(candidate)
    return tuple(candidates)


def _record(*, line: str) -> dict[str, object] | None:
    parsed = parse_json(text=line)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    mapping = cast("dict[object, object]", parsed)
    return {str(key): value for key, value in mapping.items()}


def _candidate(*, entry: object, credential_identity: str) -> SessionHeadroomBaseline | None:
    """One journaled assessment as a baseline candidate, when it can be one.

    Three things must hold, and each absence is an ordinary record rather than
    a fault: the entry is a mapping, it names THIS credential, and it carried a
    numeric utilization. A reading that was unobservable has no figure to
    subtract, so it is not a VALID assessment in the clause's sense.
    """
    if not isinstance(entry, dict):
        return None
    fields = cast("dict[object, object]", entry)
    if fields.get("credential_identity") != credential_identity:
        return None
    utilization = fields.get("utilization_percent")
    observed_at = fields.get("observed_at")
    if isinstance(utilization, bool) or not isinstance(utilization, int | float):
        return None
    if not isinstance(observed_at, str):
        return None
    return SessionHeadroomBaseline(utilization_percent=float(utilization), observed_at=observed_at)
