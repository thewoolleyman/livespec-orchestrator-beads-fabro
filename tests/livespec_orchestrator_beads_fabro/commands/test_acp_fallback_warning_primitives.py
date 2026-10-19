"""The warning and hold primitives the retired event projection used to drive.

`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded — says of the v127 retirement
that "Existing versioned hold observations, retirement records, and fallback
audit records remain readable", and that removing the engine-event dependence
"MUST NOT discard existing holds". The warning lifecycle is therefore NOT
retired with the projection: it is re-sourced from the Dispatcher's own
selection records by the sibling work-item that follows `bd-ib-qm6r1`.

THIS MODULE IS WHY THAT LIFECYCLE STAYS COVERED. Its primitives had exactly one
production caller — `_acp_event_projection`, which v127 removed — so deleting
that module's own test module took the only exercise of several of these
functions with it. Covering them here keeps the lifecycle verifiable during the
interval in which it has no caller, which is precisely the interval in which an
unexercised primitive would rot unnoticed.

EACH CASE IS PAIRED WITH THE NEAR-MISS IT MUST REFUSE, because every one of
these functions has a plausible wrong answer that looks like a correct one: a
domain-scoped failure carrying a candidate key (which `parse_hold_record`
refuses outright), a transition BACK to the primary read as a fallback, an
unknown `schema_version` read on v1's field meanings, and a retirement line
whose `warning_ids` is not a list read as retiring everything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    AcpFallbackEvent,
    event_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    AcpPrimaryAttempt,
    primary_success_clearance_records,
    read_model_fallback_warnings,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    MODEL_FALLBACK_CLEARED_STAGE,
    MODEL_FALLBACK_STAGE,
    model_fallback_warning_record,
    warning_id,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    projection_success_record,
)

_OCCURRED = "2026-09-12T12:00:00Z"
_LATER = "2026-09-12T12:05:00Z"
_GENERATION = "gen-primary-aaa"
_CHAIN = "chain-111"
_NODE = "implement"
_PRIMARY_KEY = "gpt-5-5"
_FALLBACK_KEY = "claude-haiku"
_DOMAIN = "codex"


def _identity(*, index: int, key: str) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": _DOMAIN,
    }


def _failover_payload(
    *,
    scope: str = "availability-domain",
    to_index: int = 1,
    to_key: str = _FALLBACK_KEY,
    schema_version: int = 1,
) -> dict[str, Any]:
    return {
        "type": "agent.acp.failover",
        "schema_version": schema_version,
        "event_id": "ev-1",
        "occurred_at": _OCCURRED,
        "node": _NODE,
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(index=0, key=_PRIMARY_KEY),
        "to": _identity(index=to_index, key=to_key),
        "hold_key": _DOMAIN,
        "cause": "quota",
        "scope": scope,
        "primary_generation": _GENERATION,
        "full_chain": _CHAIN,
        "attempted": [_PRIMARY_KEY],
        "skipped": [],
    }


def _one_event(**overrides: Any) -> AcpFallbackEvent:
    scan = scan_acp_events(payload=[_failover_payload(**overrides)])
    assert not isinstance(scan, str)
    [event] = scan.events
    return event


def test_a_domain_scoped_failure_carries_no_candidate_key_and_a_candidate_one_does() -> None:
    """The scope decides the key shape, and `parse_hold_record` refuses either slip."""
    domain = event_failure(event=_one_event(scope="availability-domain"))
    candidate = event_failure(event=_one_event(scope="candidate"))

    assert (domain.scope, domain.candidate_key) == ("availability-domain", None)
    assert (candidate.scope, candidate.candidate_key) == ("candidate", _PRIMARY_KEY)
    # Both read the FROM side: the hold belongs to the candidate that failed,
    # never to the one that rescued the node.
    assert domain.availability_key == _DOMAIN
    assert candidate.hold_key == _DOMAIN
    assert domain.source == "agent.acp.failover"


def test_an_unknown_schema_version_is_preserved_as_unobservable_not_read_as_v1() -> None:
    """Read on v1's field meanings it would mint a hold from fields it misread."""
    scan = scan_acp_events(payload=[_failover_payload(schema_version=2)])

    assert not isinstance(scan, str)
    assert scan.events == ()
    assert [record.get("schema_version") for record in scan.unobservable] == [2]


def test_a_warning_is_owed_for_a_fallback_and_not_for_a_return_to_the_primary() -> None:
    """A transition BACK to candidate zero executed the primary, so it owes none."""
    fell_back = model_fallback_warning_record(
        event=_one_event(to_index=1, to_key=_FALLBACK_KEY), work_item_id="bd-ib-qm6r1"
    )
    returned = model_fallback_warning_record(
        event=_one_event(to_index=0, to_key=_PRIMARY_KEY), work_item_id="bd-ib-qm6r1"
    )

    assert returned is None
    assert fell_back is not None
    assert fell_back["stage"] == MODEL_FALLBACK_STAGE
    assert fell_back["candidate_key"] == _FALLBACK_KEY
    assert fell_back["candidate_index"] == 1
    assert fell_back["primary_generation"] == _GENERATION
    assert fell_back["work_item_id"] == "bd-ib-qm6r1"
    # The id is STABLE from (event id, node), which is what makes a replay of
    # one event append nothing instead of a second row.
    assert fell_back["warning_id"] == warning_id(event_id="ev-1", node=_NODE)


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "journal.jsonl"
    _ = path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def test_a_primary_success_clears_the_live_warning_of_its_own_generation(
    tmp_path: Path,
) -> None:
    """One appendable clearance per live warning the success retires."""
    warning = model_fallback_warning_record(event=_one_event(), work_item_id="bd-ib-qm6r1")
    assert warning is not None
    ledger = read_model_fallback_warnings(
        journal_path=_journal(tmp_path=tmp_path, records=(warning,))
    )

    records = primary_success_clearance_records(
        ledger=ledger,
        attempt=AcpPrimaryAttempt(
            node=_NODE,
            primary_generation=_GENERATION,
            started_at=_LATER,
            executed=True,
            succeeded=True,
        ),
    )

    assert [record["stage"] for record in records] == [MODEL_FALLBACK_CLEARED_STAGE]
    assert [record["warning_ids"] for record in records] == [[warning["warning_id"]]]
    # The near-miss: an attempt that began BEFORE the warning was already
    # running when the fallback fired, so it is no evidence about the primary.
    older = primary_success_clearance_records(
        ledger=ledger,
        attempt=AcpPrimaryAttempt(
            node=_NODE,
            primary_generation=_GENERATION,
            started_at="2026-09-12T11:55:00Z",
            executed=True,
            succeeded=True,
        ),
    )
    assert older == ()


def test_a_well_formed_retirement_clears_its_named_warning_and_a_malformed_one_does_not(
    tmp_path: Path,
) -> None:
    """The destructive direction, asserted in both: only a readable id list clears.

    The pair is the whole case. A ledger that cleared on sight satisfies the
    well-formed half, and one that could never clear satisfies the malformed
    half; only together do they say the id list is what the fold reads.
    """
    warning = model_fallback_warning_record(event=_one_event(), work_item_id="bd-ib-qm6r1")
    assert warning is not None
    named = {
        "stage": MODEL_FALLBACK_CLEARED_STAGE,
        "node": _NODE,
        "warning_ids": [warning["warning_id"]],
    }
    malformed = {
        "stage": MODEL_FALLBACK_CLEARED_STAGE,
        "node": _NODE,
        "warning_ids": "every-warning",
    }

    cleared = read_model_fallback_warnings(
        journal_path=_journal(tmp_path=tmp_path / "cleared", records=(warning, named))
    )
    standing = read_model_fallback_warnings(
        journal_path=_journal(tmp_path=tmp_path / "standing", records=(warning, malformed))
    )

    assert cleared.warnings == ()
    assert [entry.warning_id for entry in standing.warnings] == [warning["warning_id"]]


def test_the_retired_projections_success_record_names_its_own_fact_id() -> None:
    """Covered while the record type survives; it goes with the fact that owns it.

    The projection that wrote this record is gone, and the fact the record
    resolved is retired in the next cycle of the same work-item. It is asserted
    here so the interval between the two leaves nothing unexercised.
    """
    record = projection_success_record(
        repo="livespec-orchestrator-beads-fabro",
        run_id="01M4Q8FDDHKZ3VE8WSHCTD1AKB",
        node=_NODE,
        projected=1,
        unobservable=0,
    )

    assert record["stage"] == "acp-projection-succeeded"
    assert record["fact_id"] == (
        "hygiene:model-fallback-projection:livespec-orchestrator-beads-fabro:"
        f"01M4Q8FDDHKZ3VE8WSHCTD1AKB:{_NODE}"
    )
    assert record["projected_observations"] == 1
