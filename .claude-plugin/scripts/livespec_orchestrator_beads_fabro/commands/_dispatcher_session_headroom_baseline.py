"""Reading this checkout's dispatch journal for one credential's earlier readings.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": the drain rate's baseline is "the EARLIEST assessment
carrying a valid reading journaled under this clause for the same opaque
credential identity in the dispatching checkout's dispatch journal, read
regardless of the work-item it was journaled for", observed inside the clause's
age window. This module supplies the priors; `_acp_session_headroom_drain`
decides which of them is the baseline and what the rate is, so the whole
decision stays exercisable without a journal on disk.

THE HISTORY IS THE JOURNAL THE DISPATCH IS ACTUALLY WRITING, which is why the
path is PASSED IN rather than derived from the repository root. `dispatcher.py`
accepts a `--journal` override, so a path re-derived here would read a
different file from the one this pass appends to -- a clean, plausible "no
baseline held" for a journal full of them, which is the wrong-population
reading the fleet trap catalogue describes.

FOR ANY WORK-ITEM, DELIBERATELY, and the clause says so in as many words. The
journal writes one assessment record per affected work-item per admission
evaluation, all carrying the same reading, and the quantity being measured
belongs to the CREDENTIAL rather than to any item. Scoping the history to one
item would make the rate unmeasurable for the first dispatch of every item
while an hour of readings for that same credential sat in the file.

THE IDENTITY MATCH IS WHAT MAKES THE RATE MEAN ANYTHING. Each pool slot drains
independently and `_dispatcher_factory_account_selector` can name a different
one between passes, so a baseline from another credential subtracts one
account's utilization from another's and reports the difference as a rate. The
identities are opaque digests, so the comparison is exact equality and nothing
about spelling.

EVERY UNREADABLE LINE AND EVERY ILL-SHAPED RECORD IS PASSED OVER. The journal
is append-only and is written by concurrent passes, so a truncated last line is
an ordinary state rather than a fault -- and the clause already fails the
projection open: "the journal was removed" is one of the cases it enumerates as
unavailable, and the floor still applies. Raising from here would instead fail
an admission evaluation over a figure the floor does not depend on.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    SessionHeadroomPriorReading,
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
    """This credential's baseline reading from this checkout's dispatch journal.

    An absent or not-yet-written journal is `None` rather than an error: the
    first dispatch in a fresh clone has no history, and that is the same answer
    a journal carrying nothing in the window gives.
    """
    if journal_path is None or not journal_path.is_file():
        return None
    return baseline_assessment(
        priors=_priors(
            text=journal_path.read_text(encoding="utf-8"),
            credential_identity=credential_identity,
        ),
        now_iso=now_iso,
    )


def _priors(*, text: str, credential_identity: str) -> tuple[SessionHeadroomPriorReading, ...]:
    """Every valid earlier assessment of ONE credential, in journal order."""
    priors: list[SessionHeadroomPriorReading] = []
    for line in text.splitlines():
        record = _record(line=line)
        if record is None or record.get("stage") != SESSION_HEADROOM_STAGE:
            continue
        assessments = record.get("assessments")
        if not isinstance(assessments, list):
            continue
        for entry in cast("list[object]", assessments):
            prior = _prior(entry=entry, credential_identity=credential_identity)
            if prior is not None:
                priors.append(prior)
    return tuple(priors)


def _record(*, line: str) -> dict[str, object] | None:
    parsed = parse_json(text=line)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    mapping = cast("dict[object, object]", parsed)
    return {str(key): value for key, value in mapping.items()}


def _prior(*, entry: object, credential_identity: str) -> SessionHeadroomPriorReading | None:
    """One journaled assessment as a prior reading, when it can be one.

    Three things must hold, and each absence is an ordinary record rather than
    a fault: the entry is a mapping, it names THIS credential, and it carried a
    numeric utilization. A reading that was unobservable has no figure to
    subtract, so it is not a reading the clause calls valid.

    `bool` is excluded explicitly because it is a subclass of `int`, so a
    record carrying `true` where a utilization belongs would otherwise read as
    1 percent used -- a perfectly plausible figure that says nothing about
    usage, and one that would then be subtracted from a real reading to
    manufacture a rate.
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
    return SessionHeadroomPriorReading(
        utilization_percent=float(utilization), observed_at=observed_at
    )
