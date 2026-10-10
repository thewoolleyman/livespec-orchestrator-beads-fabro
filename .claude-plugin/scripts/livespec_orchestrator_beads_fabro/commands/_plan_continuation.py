"""Reading the latest recorded plan-continuation ruling.

A continuation authorization is a ruling on the ordinary plan scope-event
timeline, never a second status store.  Only the latest ruling-shaped event
governs.  A malformed latest authorization therefore does not fall back to an
older valid one: the latest event is the maintainer's latest word, but it is not
safe authority until every required line is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    SCOPE_KIND,
    PlanTimelineEntry,
    read_timeline,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "AUTHORIZED_PREFIX",
    "REVOKED_PREFIX",
    "ContinuationRuling",
    "current_continuation_ruling",
    "current_continuation_ruling_from_entries",
    "instant_expired",
]

AUTHORIZED_PREFIX = "plan-continuation: authorized"
REVOKED_PREFIX = "plan-continuation: revoked"

_UNTIL_PREFIX = "until: "
_BY_PREFIX = "by: "
_DIRECTIVE_PREFIX = "directive: "
_RECORDED_ATTENDED_LINE = "recorded-attended: true"
_AUTHORIZED_LINE_COUNT = 5


@dataclass(frozen=True, kw_only=True)
class ContinuationRuling:
    """One complete, unexpired continuation authorization."""

    until: str
    by: str
    directive: str
    created_at: str

    @property
    def identity(self) -> str:
        """The stable human-facing identity a resume reports when it acts."""
        return f"continuation ruling by {self.by} until {self.until}"


def current_continuation_ruling(
    *, config: StoreConfig, epic_id: str, now: str
) -> ContinuationRuling | None:
    """Read the plan timeline and return its governing authorization, if current."""
    return current_continuation_ruling_from_entries(
        entries=read_timeline(config=config, epic_id=epic_id), now=now
    )


def current_continuation_ruling_from_entries(
    *, entries: Sequence[PlanTimelineEntry], now: str
) -> ContinuationRuling | None:
    """Return the latest ruling only when it is complete and unexpired."""
    shaped = [entry for entry in entries if _is_ruling(entry=entry)]
    if not shaped:
        return None
    latest = shaped[-1]
    lines = latest.body.splitlines()
    if lines[0] == REVOKED_PREFIX:
        return None
    if len(lines) < _AUTHORIZED_LINE_COUNT:
        return None
    until = _line_value(line=lines[1], prefix=_UNTIL_PREFIX)
    by = _line_value(line=lines[2], prefix=_BY_PREFIX)
    directive = _line_value(line=lines[3], prefix=_DIRECTIVE_PREFIX)
    if until is None or by is None or directive is None or lines[4] != _RECORDED_ATTENDED_LINE:
        return None
    if until != "archive" and instant_expired(until=until, now=now):
        return None
    return ContinuationRuling(
        until=until,
        by=by,
        directive=directive,
        created_at=latest.created_at,
    )


def _is_ruling(*, entry: PlanTimelineEntry) -> bool:
    if entry.kind != SCOPE_KIND:
        return False
    first = entry.body.splitlines()[0] if entry.body.splitlines() else ""
    return first in (AUTHORIZED_PREFIX, REVOKED_PREFIX)


def _line_value(*, line: str, prefix: str) -> str | None:
    if not line.startswith(prefix):
        return None
    value = line.removeprefix(prefix)
    return value if value.strip() else None


def instant_expired(*, until: str, now: str) -> bool:
    """Whether an ISO deadline is reached; malformed instants fail closed."""
    deadline = _instant(value=until)
    if deadline is None:
        return True
    observed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return observed >= deadline


def _instant(*, value: str) -> datetime | None:
    normalized = f"{value.removesuffix('Z')}+00:00" if value.endswith("Z") else value
    parsed = parse_iso_datetime(text=normalized)
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
