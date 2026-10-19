"""Reading the append-only dispatch journal as a forward sequence of objects.

The ACP fallback feature keeps two separate append-only ledgers in the
one dispatch journal -- the typed availability holds and the
model-fallback warnings -- and each is a forward fold over the same file.
The read itself is identical in both, so it lives here once: private
copies would drift, and the first divergence anyone noticed would be one
ledger tolerating a truncated line that another had started raising on.
A THIRD LEDGER USED TO SHARE IT, the projection-failure facts of the
`agent.acp.failover` projection v127 retired; its records are still in
every journal written before that retirement and are still read here as
unknown stages, which is the whole reason this fold skips what it does not
recognise rather than refusing it.

A LINE THAT DOES NOT PARSE IS SKIPPED RATHER THAN RAISED, which is the
posture `_acp_hold_ledger` already took and the reason is unchanged: the
journal is shared with every other dispatcher stage, so one truncated
line -- a crash mid-append -- must not make a whole ledger unreadable.
For the hold ledger that would send work at a live outage.
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
