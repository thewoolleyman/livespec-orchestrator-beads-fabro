"""The bounded slot hold for a run parked in a human-input-required state.

The reconciler's moot-question join releases a run the LEDGER has finished
with — the item left `active`, a newer dispatch superseded it, the item is
absent entirely. A run parked at a human gate whose item is STILL LIVE is a
different object: nobody has answered its question, and nothing in the ledger
says the answer stopped mattering. The join therefore leaves it alone, which
is exactly how one parked run held an hp scheduler slot for 164 minutes.

`dispatcher.blocked_run_grace_seconds` bounds that hold without pretending to
answer the question. Past the grace the run is exported and abandoned; the
work-item is left EXACTLY as it was, so the decision keeps waiting in the
ledger, which is the only place a human decision ever waits.

TWO FAIL-CLOSED CHOICES, both leaning toward NOT terminating.

An UNMEASURABLE park is never reaped. The parked duration is read off the
run's own record, and a record carrying none of `PARKED_SINCE_KEYS` yields
`None` rather than a guess. Such a run is still REPORTED as held — a hold
nobody can see is the failure this module exists to end — but it is not
terminated.

`start_time` is deliberately NOT one of those keys, and that is the one
judgement call worth naming. A run's AGE is an upper bound on how long it has
been parked, never the park itself: a run that started three hours ago and
parked a minute ago reads as three hours old. Measuring the park from the
run's start would reap a run parked for seconds, which is the expensive
direction. Every key below names the instant the run entered the state it is
now sitting in, so the difference from now IS the park.

Which key the pinned Fabro build (0.254.0) actually emits was NOT verifiable
where this was written: the implementation sandbox reached no factory, and no
captured `inspect` payload exists anywhere in this repo. The list is therefore
ordered most-specific-first and treated as a SEARCH rather than as a known
schema — and the fail-closed default is what makes an unmatched schema safe.
An unrecognised record leaves today's behaviour (held, reported, never
terminated) instead of reaping on a misread number. The SEARCH itself now
lives in `_fabro_record_instant`, shared with the whole-run wall budget's own
clock, which reads a different key list for a different instant; the key list
above and the fail-closed consequence of an unmatched record stay here,
because they are what this consumer decides.

The `dispatcher.blocked_run_grace_seconds` READ lives here rather than beside
the other dials in `_dispatcher_policy_settings.py`, through that module's own
public `read_dispatcher_config_value` seam — the route it documents for a
setting whose coercion is cohesive with its consumer rather than with the
reader (`dispatcher.minimum_release` sits with its floor for the same reason).
Two things make it the right home rather than the convenient one. The coercion
genuinely is peculiar to this arm: `0` is a MEANINGFUL value here and not a
degenerate one, so this setting floors at zero where every other bound in that
module floors at one. And that module stood at 242 LLOC against a 250 hard
ceiling, so the eleven lines this read costs would have breached it — a split
of that module along its own `effective_*` seam was a separate change, not a
rider on this one. That split has since landed (the per-item resolvers now sit
in `_dispatcher_policy_overrides.py`), so the size argument is spent; the
coercion argument above is what still keeps this read here.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.commands._fabro_record_instant import record_instant_epoch

__all__: list[str] = [
    "BLOCKED_HOLD_UNMEASURED",
    "BLOCKED_HOLD_WITHIN_GRACE",
    "DEFAULT_BLOCKED_RUN_GRACE_SECONDS",
    "ORPHAN_REASON_BLOCKED_PAST_GRACE",
    "PARKED_SINCE_KEYS",
    "BlockedRunGrace",
    "HeldRun",
    "grace_hold_reason",
    "measured_grace",
    "parked_seconds_from_record",
    "resolve_blocked_run_grace_seconds",
    "seconds_remaining",
]

_INSPECT_TIMEOUT_SECONDS = 60.0

DEFAULT_BLOCKED_RUN_GRACE_SECONDS = 1800
_BLOCKED_RUN_GRACE_SECONDS_KEY = "blocked_run_grace_seconds"

ORPHAN_REASON_BLOCKED_PAST_GRACE = "blocked-past-grace"
BLOCKED_HOLD_WITHIN_GRACE = "blocked-within-grace"
BLOCKED_HOLD_UNMEASURED = "blocked-park-unmeasured"

# Ordered most-specific-first; see the module docstring for why `start_time`
# is absent and why this is a search rather than a schema.
PARKED_SINCE_KEYS: tuple[str, ...] = (
    "blocked_at",
    "blocked_since",
    "parked_at",
    "last_checkpoint_at",
    "checkpoint_time",
    "updated_at",
)


@dataclass(frozen=True, kw_only=True)
class BlockedRunGrace:
    """The configured grace, plus the park measured for each governed run.

    Measurement is handed IN rather than taken here: reading a park costs a
    `fabro inspect` per run, and the classification it feeds is pure.
    """

    grace_seconds: int
    parked_seconds_by_run: Mapping[str, float | None]


@dataclass(frozen=True, kw_only=True)
class HeldRun:
    """One parked run the grace arm is holding rather than terminating.

    A held run is NOT an orphan and is never handed to the termination path:
    the two live in separate collections so that the guarantee is structural
    rather than a convention a later edit could drop.
    """

    run_id: str
    factory_name: str
    factory_server_url: str
    status_kind: str
    work_item_id: str
    work_item_status: str | None
    hold_reason: str
    parked_seconds: float | None
    seconds_remaining: float | None
    grace_seconds: int


def resolve_blocked_run_grace_seconds(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.blocked_run_grace_seconds`, defaulting to 1800.

    NOT a member of the API-configurable key manifest, deliberately. Lowering
    this dial makes the Dispatcher terminate parked runs sooner, so it is
    editable only by a committed `.livespec.jsonc` change — the same reasoning
    that keeps `require_invoker` off that surface.
    """
    return read_dispatcher_config_value(cwd=cwd, key=_BLOCKED_RUN_GRACE_SECONDS_KEY).bind_result(
        lambda value: _grace_seconds_value(value=value)
    )


def measured_grace(
    *,
    port: FabroPort,
    run_ids: Sequence[str],
    grace_seconds: int,
    now_epoch: float | None = None,
) -> BlockedRunGrace | None:
    """Measure the park of every governed run, or None when the arm is off.

    A `grace_seconds` of `0` disables the arm outright: no run is inspected,
    none is held, and classification falls back to the moot-question join
    alone. The caller names the runs worth an `inspect` rather than handing
    over the whole inventory, because each one costs a round-trip.
    """
    if grace_seconds <= 0:
        return None
    now = time.time() if now_epoch is None else now_epoch
    return BlockedRunGrace(
        grace_seconds=grace_seconds,
        parked_seconds_by_run={
            run_id: _parked_seconds(port=port, run_id=run_id, now_epoch=now) for run_id in run_ids
        },
    )


def grace_hold_reason(*, parked_seconds: float | None, grace_seconds: int) -> str:
    """Which side of the grace one measured park falls on.

    An unmeasured park is its own answer rather than a zero: reporting it as
    "within grace, 1800 seconds remaining" would promise a reap that can never
    come, because the next pass reads the same unmeasurable record.
    """
    if parked_seconds is None:
        return BLOCKED_HOLD_UNMEASURED
    if parked_seconds > grace_seconds:
        return ORPHAN_REASON_BLOCKED_PAST_GRACE
    return BLOCKED_HOLD_WITHIN_GRACE


def seconds_remaining(*, parked_seconds: float | None, grace_seconds: int) -> float | None:
    """How long a within-grace park has left, or None when it is unmeasured."""
    if parked_seconds is None:
        return None
    return max(0.0, float(grace_seconds) - parked_seconds)


def parked_seconds_from_record(
    *,
    record: Mapping[str, Any] | None,
    now_epoch: float,
) -> float | None:
    """How long this run has sat in its current state, or None if unmeasurable.

    A timestamp in the FUTURE is treated as unmeasurable rather than as a
    negative park: clock skew between the dispatching host and the factory is
    the ordinary cause, and a negative number would compare as "well within
    grace" and hide the run.
    """
    parked_at = _parked_at_epoch(record=record)
    if parked_at is None or parked_at > now_epoch:
        return None
    return now_epoch - parked_at


def _parked_seconds(*, port: FabroPort, run_id: str, now_epoch: float) -> float | None:
    inspected = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    return parked_seconds_from_record(
        record=fabro_inspect_record(payload=inspected.payload),
        now_epoch=now_epoch,
    )


def _grace_seconds_value(*, value: object) -> Result[int, PolicySettingUnreadable]:
    if value is None:
        return Success(DEFAULT_BLOCKED_RUN_GRACE_SECONDS)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=_BLOCKED_RUN_GRACE_SECONDS_KEY,
            detail=(
                f"dispatcher.{_BLOCKED_RUN_GRACE_SECONDS_KEY} must be an integer >= 0; "
                f"got {value!r}"
            ),
        )
    )


def _parked_at_epoch(*, record: Mapping[str, Any] | None) -> float | None:
    """The instant this run entered its current state, from its own record.

    The SEARCH mechanics live in `_fabro_record_instant`, shared with the
    whole-run wall budget's own clock; `PARKED_SINCE_KEYS` above is what this
    consumer contributes to it, and the module docstring carries why
    `start_time` is absent from that list.
    """
    return record_instant_epoch(record=record, keys=PARKED_SINCE_KEYS)
