"""The fold that turns the dispatch journal's records into each subject's current hold.

Split out of `_needs_attention_journal_hold` by cohesion: this module is the PURE
half — it reads no file and composes no fact — and that module owns the one read
of the journal and the facts built from what this fold establishes. The ratified
"Journal-recorded holds" clause in `SPECIFICATION/contracts.md` is the rule this
implements.

A RECORD IS OF A SUBJECT WHEN IT NAMES THAT SUBJECT UNDER ANY OF THE FOUR KEYS,
but a hold takes the value of the FIRST key it carries as its own subject, in the
clause's order. A hold is therefore filed under one subject only, while a
retiring record reaches every subject it names — which is what lets a terminal
record naming an item and a run retire a hold filed under either.

THREE STAGES ARE EXCLUDED IN PART, not wholly. A `stranded-claim-hold`, a
`sandbox-container-held` and a release hold are written for situations that are
not holds when their recorded reason says the owner is live or the release
already happened, and such a record also RETIRES an earlier hold of its own
stage for that subject. It touches no other stage, so a `recovery-held` record
survives a later excluded record of a different stage.

A STAGE REPEATED ON EVERY PASS IS ONE HOLD, read from its newest record, and its
seven days run from that record. The newest record of a subject is the newest by
append order, which is what the journal's single writer guarantees.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "HOLD_STAGES",
    "RECOVERY_HELD_STAGE",
    "RETIRING_STAGES",
    "FoldedHolds",
    "JournalHold",
    "fold_journal_holds",
]

RECOVERY_HELD_STAGE = "recovery-held"

HOLD_STAGES: frozenset[str] = frozenset(
    {
        RECOVERY_HELD_STAGE,
        "publish-branch-reclaim-held",
        "run-wall-budget-held",
        "stall-cancel-release-held",
        "provider-limit-release-held",
        "stranded-claim-hold",
        "orphan-run-reconcile-held",
        "sandbox-container-held",
        "incident-proof-pointer-refused",
        "acp-availability-observed-refused",
        "launcher-hold",
    }
)

_LAUNCHER_HOLD = "launcher-hold"
_LAUNCHER_HOLD_LIFTED = "launcher-hold-lifted"

RETIRING_STAGES: frozenset[str] = frozenset(
    {
        "recovery-route",
        "dispatch-id",
        "dispatch-run-stamp",
        "resume",
        "stall-cancel-release",
        "provider-limit-release",
        "ledger-admit-release",
        "publish-branch-reclaim",
        "orphan-run-reconciled",
        "stranded-claim-release",
        "stranded-claim-run-absent-repeated",
        "stranded-claim-terminal-completion",
        "run-wall-budget-exceeded",
        "run-wall-budget-needs-human",
        "fabro-terminal-events",
        "needs-human-blocked",
        "stall-cancel-needs-human",
        "ledger-complete",
        "ended-run-collected",
        "sandbox-container-reclaimed",
        _LAUNCHER_HOLD_LIFTED,
    }
)

# The order is the clause's: the first key a record carries names its subject.
_SUBJECT_KEYS: tuple[str, ...] = ("work_item_id", "run_id", "container_name", "hold")
_REASON_KEYS: tuple[str, ...] = (
    "reason",
    "hold_reason",
    "failed_measurement",
    "measurements",
    "refusals",
    "detail",
    "details",
)
_STRANDED_NOT_A_HOLD: tuple[str, ...] = ("run-live", "dispatch-live", "claim-changed")
_RELEASE_HOLD_STAGES: tuple[str, ...] = ("stall-cancel-release-held", "provider-limit-release-held")
_WINDOW = timedelta(days=7)
_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True, kw_only=True)
class JournalHold:
    """One subject's current hold: the stage and the reason keys its record carried."""

    subject: str
    subject_key: str
    stage: str
    appended_at: str
    reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True, kw_only=True)
class FoldedHolds:
    """The current holds, and the items carrying a live `recovery-held`."""

    holds: tuple[JournalHold, ...]
    live_recovery_held_ids: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class _Entry:
    index: int
    subject_key: str
    record: dict[str, object]


def fold_journal_holds(
    *,
    records: Iterable[dict[str, object]],
    closed: Collection[str],
    now: datetime,
) -> FoldedHolds:
    """Fold the records, in append order, into each subject's current hold."""
    state: dict[str, dict[str, _Entry]] = {}
    for index, record in enumerate(records):
        _apply(state=state, index=index, record=record)
    holds = tuple(
        _current_hold(subject=subject, group=group)
        for subject, group in sorted(state.items())
        if group and subject not in closed and _is_current(entry=_newest(group=group), now=now)
    )
    live_recovery = frozenset(
        subject
        for subject, group in state.items()
        if RECOVERY_HELD_STAGE in group
        and subject not in closed
        and _is_current(entry=group[RECOVERY_HELD_STAGE], now=now)
    )
    return FoldedHolds(holds=holds, live_recovery_held_ids=live_recovery)


def _apply(*, state: dict[str, dict[str, _Entry]], index: int, record: dict[str, object]) -> None:
    stage = record.get("stage")
    if not isinstance(stage, str):
        return
    named = _named(record=record)
    if stage in RETIRING_STAGES:
        for _key, subject in named:
            group = state.get(subject)
            if group is None:
                continue
            if stage == _LAUNCHER_HOLD_LIFTED:
                _ = group.pop(_LAUNCHER_HOLD, None)
            else:
                group.clear()
    elif stage in HOLD_STAGES and named:
        key, subject = named[0]
        if _is_excluded(stage=stage, record=record):
            group = state.get(subject)
            if group is not None:
                _ = group.pop(stage, None)
        else:
            state.setdefault(subject, {})[stage] = _Entry(
                index=index, subject_key=key, record=record
            )


def _named(*, record: dict[str, object]) -> list[tuple[str, str]]:
    named: list[tuple[str, str]] = []
    for key in _SUBJECT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            named.append((key, value))
    return named


def _is_excluded(*, stage: str, record: dict[str, object]) -> bool:
    if stage == "stranded-claim-hold":
        return record.get("reason") in _STRANDED_NOT_A_HOLD
    if stage == "sandbox-container-held":
        return record.get("hold_reason") == "run-live"
    if stage in _RELEASE_HOLD_STAGES:
        return record.get("reason") == "already-released"
    return False


def _newest(*, group: dict[str, _Entry]) -> _Entry:
    return max(group.values(), key=lambda entry: entry.index)


def _is_current(*, entry: _Entry, now: datetime) -> bool:
    """Whether the record was appended within the window.

    A record whose `at` cannot be read is treated as current: the append layer
    stamps every record, so an unreadable stamp is a torn or foreign line, and
    retiring a hold on a measurement nobody took would report it resolved.
    """
    stamped = entry.record.get("at")
    if not isinstance(stamped, str):
        return True
    parsed = attempt(
        action=lambda: datetime.strptime(stamped, _AT_FORMAT), exceptions=(ValueError,)
    )
    if isinstance(parsed, AttemptFailure):
        return True
    return now - parsed.replace(tzinfo=timezone.utc) <= _WINDOW


def _current_hold(*, subject: str, group: dict[str, _Entry]) -> JournalHold:
    entry = _newest(group=group)
    record = entry.record
    return JournalHold(
        subject=subject,
        subject_key=entry.subject_key,
        stage=str(record["stage"]),
        appended_at=str(record.get("at", "")),
        reasons=tuple((key, _rendered(value=record[key])) for key in _REASON_KEYS if key in record),
    )


def _rendered(*, value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)
