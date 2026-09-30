"""Reading the append-only dispatch journal as a forward sequence of objects.

The ACP fallback feature keeps three separate append-only ledgers in the
one dispatch journal -- the typed availability holds, the model-fallback
warnings, and the projection-failure facts -- and each is a forward fold
over the same file. The read itself is identical in all three, so it
lives here once: three private copies would drift, and the first
divergence anyone noticed would be one ledger tolerating a truncated line
that another had started raising on.

A LINE THAT DOES NOT PARSE IS SKIPPED RATHER THAN RAISED, which is the
posture `_acp_hold_ledger` already took and the reason is unchanged: the
journal is shared with every other dispatcher stage, so one truncated
line -- a crash mid-append -- must not make a whole ledger unreadable.
For the hold ledger that would send work at a live outage; for the
projection ledger it would hide the very fact that stops the drain.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "journal_records",
]


def journal_records(*, journal_path: Path | None) -> tuple[Mapping[str, Any], ...]:
    """Every readable JSON object in the journal, in file order.

    An absent path and an unreadable file both yield the empty sequence:
    a repository that has never dispatched has no journal, and that is
    not a failure to report -- every caller here treats "no records" as
    "no ledger state", which is exactly right for both.
    """
    if journal_path is None or not journal_path.is_file():
        return ()
    text = attempt(action=lambda: journal_path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return ()
    records: list[Mapping[str, Any]] = []
    for line in text.splitlines():
        parsed = parse_json(text=line)
        if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
            continue
        records.append({str(key): value for key, value in cast("dict[str, Any]", parsed).items()})
    return tuple(records)
