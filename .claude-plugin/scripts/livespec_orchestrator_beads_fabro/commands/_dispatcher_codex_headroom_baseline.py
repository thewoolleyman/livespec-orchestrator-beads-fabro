"""This checkout's journal, read for ONE Codex credential's earlier windows.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": the projection uses "exactly the baseline, drain-rate,
unavailable-projection, and horizon rules of the Claude clause, applied per
opaque credential identity AND per window length, so a reading of one window is
never a baseline for another".

THE PER-WINDOW SCOPING IS THE WHOLE OF THIS MODULE. Its Claude sibling matches
on the credential identity alone, because that clause has exactly one window;
here a credential reports up to two, they drain at completely different rates,
and a baseline matched on the credential alone would subtract a weekly window's
spend from a five-hour window's and report the difference as the five-hour
window's rate. Nothing in the record would look wrong: both figures are real
readings of the same credential.

THE HISTORY IS THE JOURNAL THE DISPATCH IS ACTUALLY WRITING, which is why the
path is PASSED IN rather than derived from the repository root. `dispatcher.py`
accepts a `--journal` override, so a path re-derived here would read a different
file from the one this pass appends to -- a clean, plausible "no baseline held"
for a journal full of them.

IT READS THE SAME STAGE THE CLAUDE BASELINE DOES, under this clause's own key.
One record per work-item per evaluation carries both providers' readings, so
there is one stage to recognise and the two reads differ only in which key they
walk. A separate stage would have made every reader of the journal learn a
second record shape to answer "what did this evaluation assess".

EVERY UNREADABLE LINE AND EVERY ILL-SHAPED RECORD IS PASSED OVER, exactly as in
the Claude read. The journal is append-only and written by concurrent passes, so
a truncated last line is an ordinary state rather than a fault -- and the clause
already fails the projection OPEN, with the floor still applying. Raising from
here would instead fail an admission evaluation over a figure no floor depends
on.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom_records import (
    CODEX_ASSESSMENTS_KEY,
)
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
    "codex_window_baselines",
]


def codex_window_baselines(
    *,
    journal_path: Path | None,
    credential_identity: str,
    window_seconds: tuple[int, ...],
    now_iso: str,
) -> dict[int, SessionHeadroomBaseline]:
    """One baseline per window length this reading carries, where history supports one.

    A window with no in-window prior is ABSENT from the mapping rather than
    present with a null, which is what makes the projection's own lookup the
    whole of the per-window rule: `baselines.get(...)` answers `None` and the
    projection reports an unavailable result naming the absent baseline.

    An absent or not-yet-written journal yields the empty mapping, which is the
    same answer a journal carrying nothing in the window gives -- the first
    dispatch in a fresh clone has no history, and the clause enumerates exactly
    that as an unavailable projection rather than a fault.
    """
    if journal_path is None or not journal_path.is_file():
        return {}
    text = journal_path.read_text(encoding="utf-8")
    found: dict[int, SessionHeadroomBaseline] = {}
    for seconds in window_seconds:
        baseline = baseline_assessment(
            priors=_priors(
                text=text, credential_identity=credential_identity, window_seconds=seconds
            ),
            now_iso=now_iso,
        )
        if baseline is not None:
            found[seconds] = baseline
    return found


def _priors(
    *, text: str, credential_identity: str, window_seconds: int
) -> tuple[SessionHeadroomPriorReading, ...]:
    """Every earlier reading of ONE credential's ONE window, in journal order."""
    priors: list[SessionHeadroomPriorReading] = []
    for line in text.splitlines():
        record = _record(line=line)
        if record is None or record.get("stage") != SESSION_HEADROOM_STAGE:
            continue
        entries = record.get(CODEX_ASSESSMENTS_KEY)
        if not isinstance(entries, list):
            continue
        for entry in cast("list[object]", entries):
            prior = _prior(
                entry=entry,
                credential_identity=credential_identity,
                window_seconds=window_seconds,
            )
            if prior is not None:
                priors.append(prior)
    return tuple(priors)


def _record(*, line: str) -> dict[str, object] | None:
    parsed = parse_json(text=line)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    mapping = cast("dict[object, object]", parsed)
    return {str(key): value for key, value in mapping.items()}


def _prior(
    *, entry: object, credential_identity: str, window_seconds: int
) -> SessionHeadroomPriorReading | None:
    """One journaled assessment's ONE window as a prior, when it can be one.

    Three things must hold, and each absence is an ordinary record rather than a
    fault: the entry is a mapping, it names THIS credential, and it carries a
    numeric `used_percent` for a window of THIS length. A reading that was
    unobservable carries no window at all, so it is not a reading the clause
    calls valid.
    """
    if not isinstance(entry, dict):
        return None
    fields = cast("dict[object, object]", entry)
    if fields.get("credential_identity") != credential_identity:
        return None
    observed_at = fields.get("observed_at")
    if not isinstance(observed_at, str):
        return None
    used = _used_percent(windows=fields.get("windows"), window_seconds=window_seconds)
    if used is None:
        return None
    return SessionHeadroomPriorReading(utilization_percent=used, observed_at=observed_at)


def _used_percent(*, windows: object, window_seconds: int) -> float | None:
    """The spend one recorded entry reports for ONE window length, or `None`.

    `bool` is excluded explicitly from BOTH fields because it is a subclass of
    `int`: a record carrying `true` where a percentage belongs would read as 1
    percent used -- a plausible figure that would then be subtracted from a real
    reading to manufacture a rate -- and `true` where a span belongs would match
    a window length of one second that no reading can ever carry.
    """
    if not isinstance(windows, list):
        return None
    for window in cast("list[object]", windows):
        if not isinstance(window, dict):
            continue
        fields = cast("dict[object, object]", window)
        seconds = fields.get("limit_window_seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds != window_seconds:
            continue
        used = fields.get("used_percent")
        if isinstance(used, bool) or not isinstance(used, int | float):
            continue
        return float(used)
    return None
