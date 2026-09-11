"""The append-only journal of observed ACP availability holds.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Bounded expiry, later matching execution, and operator
clearance are the only hold-retirement routes. A node attempt that starts
after a domain observation and succeeds against the same hold key retires
only that older domain record; a later success by the exact candidate
identity retires only its older candidate record. A successful fallback
MUST NOT clear its skipped or failed primary, even when the whole run
succeeds."

NOTHING IS EVER REWRITTEN OR DELETED, which is the same discipline the
legacy provider journal already keeps: a retirement is an APPENDED line
naming the observation it retires. What was observed, and what retired
it, survive as separate readable facts.

THE READ IS A FORWARD FOLD, NOT A NEWEST-FIRST SCAN, and that choice is
what makes ingestion idempotent. Observations land in a dict keyed by
`observation_id` with FIRST WRITE WINNING, so re-projecting the same
`agent.acp.failover` event neither duplicates the record nor replaces its
stored `expires_at` with a later one -- the contract's "repeated
ingestion cannot refresh expiry" falls out of the data structure rather
than out of a rule somebody has to enforce.

RETIREMENT ADDRESSES AN OBSERVATION ID, NOT A TRIPLE, even though an
operator clears by scope and key. The clearing surface resolves the live
targets first -- it has to, because it must refuse a nonexistent one --
so it already knows the ids. Naming them makes the retirement exact:
an observation minted AFTER the clearance, from a genuinely new attempt,
carries a new id and is untouched, with no timestamp comparison to get
wrong.

AN UNKNOWN SCHEMA VERSION IS KEPT, NOT DROPPED. It rides out on
`unobservable` with its raw payload intact, so a caller can surface it;
it mints no hold and is never read on v1's field meanings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import DOMAIN_SCOPE
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_STAGE,
    AcpAvailabilityHold,
    hold_expired,
    parse_hold_instant,
    parse_hold_record,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "CLEARED_STAGE",
    "RETIRED_STAGE",
    "AcpHoldLedger",
    "AcpSuccessfulAttempt",
    "acp_hold_clearance_record",
    "ingest_hold_observation",
    "live_holds_for_target",
    "read_acp_hold_ledger",
    "retired_by_success",
    "success_retirement_records",
]

# The operator's exact valve, kept distinct from the legacy
# `provider-exhaustion-cleared` stage so the two can never retire each
# other's records: "the legacy provider valve addresses legacy records
# only."
CLEARED_STAGE = "acp-availability-cleared"
RETIRED_STAGE = "acp-availability-retired"

_RETIREMENT_STAGES = frozenset({CLEARED_STAGE, RETIRED_STAGE})


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class AcpSuccessfulAttempt:
    """One candidate attempt that STARTED and then SUCCEEDED.

    `started_at` is the attempt's start, never its finish, because the
    contract's retirement rule is "a node attempt that STARTS after a
    domain observation and succeeds". An attempt already running when the
    outage was observed proves nothing about it.

    `domain_keys` is the succeeding candidate's whole domain set -- its
    `availability_key` plus every override its domain signatures declare
    -- as `_acp_hold_coverage.candidate_domain_keys` computes it.
    """

    availability_key: str
    candidate_key: str
    domain_keys: frozenset[str]
    started_at: str


@dataclass(frozen=True, kw_only=True)
class AcpHoldLedger:
    """Every live typed hold, plus what could not be read as one."""

    holds: tuple[AcpAvailabilityHold, ...]
    unobservable: tuple[Mapping[str, object], ...]
    observation_ids: frozenset[str]


def read_acp_hold_ledger(*, journal_path: Path | None, now_iso: str) -> AcpHoldLedger:
    """Fold the journal into the holds that still stand right now."""
    observations: dict[str, AcpAvailabilityHold] = {}
    unobservable: list[Mapping[str, object]] = []
    seen: set[str] = set()
    retired: set[str] = set()
    for record in _records(journal_path=journal_path):
        stage = record.get("stage")
        if stage in _RETIREMENT_STAGES:
            retired.update(_retired_ids(record=record))
            continue
        if stage != HOLD_STAGE:
            continue
        parsed = parse_hold_record(record=record)
        if isinstance(parsed, str):
            unobservable.append(record)
            continue
        seen.add(parsed.observation_id)
        # FIRST WRITE WINS: a re-ingested observation must not refresh
        # the stored expiry, which is what makes projection idempotent.
        _ = observations.setdefault(parsed.observation_id, parsed)
    live = tuple(
        hold
        for key, hold in observations.items()
        if key not in retired and not hold_expired(hold=hold, now_iso=now_iso)
    )
    return AcpHoldLedger(
        holds=live, unobservable=tuple(unobservable), observation_ids=frozenset(seen)
    )


def ingest_hold_observation(
    *, record: dict[str, object], ledger: AcpHoldLedger, journal: _Journal
) -> bool:
    """Append one observation unless this exact one is already recorded.

    Dedupe reads `observation_ids` -- every observation the journal has
    EVER carried -- rather than the live set. Checking live holds would
    let an expired or retired observation be re-appended by the same
    evidence, resurrecting a hold an operator had already cleared.
    """
    identifier = record.get("observation_id")
    if isinstance(identifier, str) and identifier in ledger.observation_ids:
        return False
    journal.append(record=record)
    return True


def live_holds_for_target(
    *, ledger: AcpHoldLedger, scope: str, hold_key: str, candidate_key: str | None
) -> tuple[AcpAvailabilityHold, ...]:
    """Every live hold on one EXACT scope and key, in observation order."""
    return tuple(hold for hold in ledger.holds if hold.target == (scope, hold_key, candidate_key))


def acp_hold_clearance_record(
    *,
    scope: str,
    hold_key: str,
    candidate_key: str | None,
    reason: str,
    observation_ids: tuple[str, ...],
) -> dict[str, object]:
    """Build the appended line an operator's exact clearance writes.

    `at`, `invoker` and `invoker_source` are stamped by the append layer,
    which is what makes "who cleared it, and when" an unforgeable claim
    on this record rather than one its writer chose.
    """
    return {
        "stage": CLEARED_STAGE,
        "scope": scope,
        "hold_key": hold_key,
        "candidate_key": candidate_key,
        "reason": reason,
        "observation_ids": list(observation_ids),
    }


def retired_by_success(*, hold: AcpAvailabilityHold, success: AcpSuccessfulAttempt) -> bool:
    """Whether a later matching success falsifies this one record.

    Three conditions, each of which the contract states separately:

    - the attempt STARTED after the observation, so an attempt already
      running when the outage was seen retires nothing;
    - a DOMAIN record is retired only when the succeeding candidate
      belongs to that very hold key;
    - a CANDIDATE record is retired only by its own exact identity pair,
      which is what makes "a successful fallback MUST NOT clear its
      skipped or failed primary" hold without a rule of its own -- the
      fallback's pair is simply not the primary's.
    """
    if not _starts_after(hold=hold, started_at=success.started_at):
        return False
    if hold.scope == DOMAIN_SCOPE:
        return hold.hold_key in success.domain_keys
    return (hold.hold_key, hold.candidate_key) == (
        success.availability_key,
        success.candidate_key,
    )


def success_retirement_records(
    *, ledger: AcpHoldLedger, success: AcpSuccessfulAttempt
) -> tuple[dict[str, object], ...]:
    """One appendable retirement per live hold this success falsifies."""
    return tuple(
        {
            "stage": RETIRED_STAGE,
            "scope": hold.scope,
            "hold_key": hold.hold_key,
            "candidate_key": hold.candidate_key,
            "observation_ids": [hold.observation_id],
            "retired_by_candidate_key": success.candidate_key,
            "retired_by_availability_key": success.availability_key,
            "attempt_started_at": success.started_at,
        }
        for hold in ledger.holds
        if retired_by_success(hold=hold, success=success)
    )


def _starts_after(*, hold: AcpAvailabilityHold, started_at: str) -> bool:
    """Whether the attempt began strictly after this observation occurred.

    An unreadable start instant reports False, keeping the hold: a
    retirement is the destructive direction, so a clock nobody can read
    must not be allowed to authorise one.
    """
    occurred = parse_hold_instant(text=hold.occurred_at)
    started = parse_hold_instant(text=started_at)
    if occurred is None or started is None:
        return False
    return started > occurred


def _retired_ids(*, record: Mapping[str, Any]) -> frozenset[str]:
    """The observation ids one retirement or clearance line names."""
    raw = record.get("observation_ids")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item for item in cast("list[object]", raw) if isinstance(item, str))


def _records(*, journal_path: Path | None) -> tuple[Mapping[str, Any], ...]:
    """Every readable JSON object in the journal, in file order.

    A line that does not parse is SKIPPED rather than raising: the
    journal is shared with every other dispatcher stage, and one
    truncated line -- a crash mid-append -- must not make the whole hold
    ledger unreadable and send work at a live outage.
    """
    if journal_path is None or not journal_path.is_file():
        return ()
    records: list[Mapping[str, Any]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_json(text=line)
        if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
            continue
        records.append({str(key): value for key, value in cast("dict[str, Any]", parsed).items()})
    return tuple(records)
