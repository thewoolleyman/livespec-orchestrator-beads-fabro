"""Carrier-specific causal supersession refusal logic."""

from __future__ import annotations

from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import CLOSED_STATUS
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import parse_result_reference
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ItemStatusTarget,
    ResultReference,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = ["carrier_refusal_detail"]


def carrier_refusal_detail(
    *,
    carrier_id: str,
    mapped: bool,
    status: str,
    closed_at: str | None,
    derived_at: str,
    replacement: object,
) -> str | None:
    """The verified carrier refusal detail, or ``None`` when it admits the replacement."""
    if not mapped:
        return (
            f"carrier {carrier_id!r} is not named by the epic's latest carrier-map scope "
            "event, so its state is evidence about nothing this plan asserted"
        )
    if status == CLOSED_STATUS:
        if _closed_by(closed_at=closed_at, instant=derived_at):
            return (
                f"carrier {carrier_id!r} was already closed when the derivation was recorded "
                f"at {derived_at}, so the derived step could legitimately have been taken"
            )
        return (
            f"carrier {carrier_id!r} is closed now, so the replacement result is already "
            "satisfied and no obligation may be traded for it"
        )
    parsed = parse_result_reference(value=replacement)
    if (
        isinstance(parsed, ResultReference)
        and isinstance(parsed.target, ItemStatusTarget)
        and parsed.target.item_id == carrier_id
        and parsed.target.status == CLOSED_STATUS
    ):
        return None
    return (
        "the replacement result must be the closure of the carrier the evidence names, "
        f"{carrier_id!r}: a carrier is evidence for waiting on that carrier and for nothing else"
    )


def _closed_by(*, closed_at: str | None, instant: str) -> bool:
    """Whether a closure is recorded at or before an instant, failing closed."""
    if closed_at is None:
        return True
    closed = _utc(value=closed_at)
    derived = _utc(value=instant)
    return closed is None or derived is None or closed <= derived


def _utc(*, value: str) -> datetime | None:
    """One aware UTC instant, or ``None`` when it cannot be safely compared."""
    parsed = parse_iso_datetime(text=value.replace("Z", "+00:00"))
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed
