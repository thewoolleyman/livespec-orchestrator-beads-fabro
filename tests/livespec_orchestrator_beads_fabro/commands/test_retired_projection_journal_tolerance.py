"""One journal, every retired projection record, and every surviving reader.

Binds the fifth Definition-of-Done assertion of work-item `bd-ib-qm6r1` against
`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded: "Existing versioned hold
observations, retirement records, and fallback audit records remain readable.
Removing dependence on new engine failover events MUST NOT discard existing
holds or reinterpret unknown record versions."

WHY ONE JOURNAL RATHER THAN ONE PER READER. The claim is about a real file, and
a real file holds every writer's records interleaved: this repository's own
journal held 153 unresolved `acp-projection-failure` records beside its live
holds and warnings when the retirement was measured. A per-reader fixture
carrying only that reader's own stages cannot fail for the reason this case
exists — it would never put a retired record in front of the reader at all.

EVERY READER IS ASSERTED TO RETURN ITS LIVE SET, not merely to avoid raising.
"Still parses" is satisfied by a reader that swallows the file and reports
nothing, which is the failure mode that matters: a hold silently discarded is a
candidate silently re-dispatched into an outage. So each reader's expected
answer is spelled out, and the retired records' PRESENCE in the raw read is
asserted too — the records are history and the retirement must not rewrite them.

THE UNKNOWN-VERSION ARM IS THE CLAUSE'S OWN WORDING. A hold observation
carrying a `schema_version` this build does not know must come back
UNINTERPRETED rather than read on v1's field meanings, and its entitlements must
stay unconfirmed rather than being scoped from a field nobody may read.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    read_model_fallback_warnings,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import (
    CLEARED_STAGE,
    read_acp_hold_ledger,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_SCHEMA_VERSION,
    HOLD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_FACT_MODULE = "_acp_projection_failure"

# The legacy provider-exhaustion reader is reached LAZILY, exactly as the
# unit-tier modules that read `_dispatcher_acp_preflight` do: its module sits on
# a module-level cycle through `_dispatcher_engine`, so it cannot be the first
# member of the `_dispatcher_*` family a fresh interpreter imports.
_EXHAUSTION_MODULE = "_dispatcher_provider_exhaustion"

_OCCURRED = "2026-09-12T12:00:00Z"
_WITHIN_EXPIRY = "2026-09-12T12:10:00Z"
_EXPIRES = "2026-09-12T12:15:00Z"
_REPO_NAME = "livespec-orchestrator-beads-fabro"
_RUN_ID = "01M4Q8FDDHKZ3VE8WSHCTD1AKB"
_NODE = "implement"
_FACT_ID = f"hygiene:model-fallback-projection:{_REPO_NAME}:{_RUN_ID}:{_NODE}"

_LIVE_OBSERVATION_ID = "acpobs-live"
_UNKNOWN_OBSERVATION_ID = "acpobs-v99"
_CLEARED_OBSERVATION_ID = "acpobs-cleared"

# Every stage the retired projection and its loop gate ever appended. Spelled as
# literals because all five writers are gone: a constant imported from the
# product would be a dependency on exactly the modules this retirement removed,
# and these strings are what the records ALREADY on disk carry.
_RETIRED_STAGES: tuple[str, ...] = (
    "acp-projection-failure",
    "acp-projection-succeeded",
    "acp-projection-failure-cleared",
    "acp-projection-picking-stopped",
    "acp-projection-warning-surfaced",
    "acp-projection-hook-error",
)


def _retired_projection_lines() -> tuple[dict[str, Any], ...]:
    """One line per retired stage, in the shape each writer appended."""
    return (
        {
            "at": _OCCURRED,
            "invoker": "machine:dispatcher",
            "stage": "acp-projection-failure",
            "fact_id": _FACT_ID,
            "repo": _REPO_NAME,
            "run_id": _RUN_ID,
            "node": _NODE,
            "factory_name": "petri",
            "factory_server_url": "https://gmktec.perch-rudd.ts.net:32276",
            "reason": "timed-out",
            "exit_code": 124,
        },
        {
            "at": _OCCURRED,
            "invoker": "machine:dispatcher",
            "stage": "acp-projection-succeeded",
            "fact_id": _FACT_ID,
            "repo": _REPO_NAME,
            "run_id": _RUN_ID,
            "node": _NODE,
            "projected_observations": 1,
            "unobservable_events": 0,
        },
        {
            "at": _OCCURRED,
            "invoker": "human:tester",
            "stage": "acp-projection-failure-cleared",
            "fact_id": _FACT_ID,
            "reason": "the factory was decommissioned",
        },
        {
            "at": _OCCURRED,
            "invoker": "machine:dispatcher",
            "stage": "acp-projection-picking-stopped",
            "fact_ids": [_FACT_ID],
            "attended": False,
        },
        {
            "at": _OCCURRED,
            "invoker": "human:tester",
            "stage": "acp-projection-warning-surfaced",
            "fact_ids": [_FACT_ID],
            "attended": True,
        },
        {
            "at": _OCCURRED,
            "invoker": "machine:dispatcher",
            "stage": "acp-projection-hook-error",
            "work_item_id": "bd-ib-qm6r1",
            "fabro_run_id": _RUN_ID,
            "reason": "OSError",
        },
    )


def _hold_line(*, observation_id: str, schema_version: int = HOLD_SCHEMA_VERSION) -> dict[str, Any]:
    """One versioned availability observation, as the hold writer appends it."""
    return {
        "at": _OCCURRED,
        "invoker": "machine:dispatcher",
        "stage": HOLD_STAGE,
        "schema_version": schema_version,
        "observation_id": observation_id,
        "scope": "availability-domain",
        "hold_key": "codex",
        "candidate_key": None,
        "cause": "quota",
        "evidence_kind": "acp-failover-event",
        "evidence_id": f"ev-{observation_id}",
        "occurred_at": _OCCURRED,
        "expires_at": _EXPIRES,
        "work_item_id": "bd-ib-qm6r1",
        "node": _NODE,
    }


def _hold_clearance_line() -> dict[str, Any]:
    """The retirement record that retires ONE of those observations."""
    return {
        "at": _OCCURRED,
        "invoker": "human:tester",
        "stage": CLEARED_STAGE,
        "scope": "availability-domain",
        "hold_key": "codex",
        "candidate_key": None,
        "observation_ids": [_CLEARED_OBSERVATION_ID],
        "reason": "the allowance was restored out of band",
    }


def _warning_line() -> dict[str, Any]:
    """One fallback audit record: the warning the clause keeps readable."""
    return {
        "at": _OCCURRED,
        "invoker": "machine:dispatcher",
        "stage": "acp-model-fallback-observed",
        "schema_version": 1,
        "warning_id": "acpwarn-live",
        "node": _NODE,
        "occurred_at": _OCCURRED,
        "candidate_display_name": "GLM ACP Agent GLM 5.1",
        "candidate_key": "glm-5-1",
        "availability_key": "codex",
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "event_id": "ev-live",
        "candidate_index": 1,
        "work_item_id": "bd-ib-qm6r1",
    }


def _exhaustion_line() -> dict[str, Any]:
    """One legacy provider-exhaustion record, the oldest reader's own shape."""
    return {
        "at": _OCCURRED,
        "invoker": "machine:dispatcher",
        "stage": "provider-exhaustion-observed",
        "provider": "codex",
        "credential_identity": None,
        "governing_condition": "provider-usage-limit",
        "record_expires_at": _EXPIRES,
        "work_item_id": "bd-ib-qm6r1",
    }


def _mixed_journal(*, tmp_path: Path) -> Path:
    """One file holding every retired record beside every surviving one."""
    records: tuple[dict[str, Any], ...] = (
        *_retired_projection_lines(),
        _hold_line(observation_id=_LIVE_OBSERVATION_ID),
        _hold_line(observation_id=_CLEARED_OBSERVATION_ID),
        _hold_line(observation_id=_UNKNOWN_OBSERVATION_ID, schema_version=99),
        _hold_clearance_line(),
        _warning_line(),
        _exhaustion_line(),
    )
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    _ = path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def test_the_projection_failure_fact_module_is_gone_and_unimportable() -> None:
    """The fact the retired records named has no code left that reads it."""
    assert not (_COMMANDS / f"{_FACT_MODULE}.py").is_file()
    assert importlib.util.find_spec(f"{_PACKAGE}.{_FACT_MODULE}") is None


def test_the_raw_read_still_yields_every_line_including_the_retired_ones(
    tmp_path: Path,
) -> None:
    """The records are history: the retirement must not rewrite the file."""
    records = list(journal_records(journal_path=_mixed_journal(tmp_path=tmp_path)))

    assert len(records) == 12
    retired = [str(record.get("stage")) for record in records if record.get("fact_id") is not None]
    assert retired == [
        "acp-projection-failure",
        "acp-projection-succeeded",
        "acp-projection-failure-cleared",
    ]
    assert {str(record.get("stage")) for record in records} >= set(_RETIRED_STAGES)


def test_the_hold_ledger_reports_the_live_hold_and_retires_only_the_named_one(
    tmp_path: Path,
) -> None:
    """A hold silently discarded is a candidate silently re-dispatched."""
    ledger = read_acp_hold_ledger(
        journal_path=_mixed_journal(tmp_path=tmp_path), now_iso=_WITHIN_EXPIRY
    )

    assert [hold.observation_id for hold in ledger.holds] == [_LIVE_OBSERVATION_ID]
    assert _CLEARED_OBSERVATION_ID in ledger.retired_observation_ids


def test_an_unknown_record_version_comes_back_uninterpreted_and_confirms_nothing(
    tmp_path: Path,
) -> None:
    """The clause's own wording: never reinterpreted on v1's field meanings."""
    ledger = read_acp_hold_ledger(
        journal_path=_mixed_journal(tmp_path=tmp_path), now_iso=_WITHIN_EXPIRY
    )

    assert [record.get("observation_id") for record in ledger.unobservable] == [
        _UNKNOWN_OBSERVATION_ID
    ]
    # Its `hold_key` is PRESENT in the record and must not have been read: a
    # skip scoped from it would be exactly the reinterpretation forbidden.
    assert ledger.unconfirmed_keys == frozenset()


def test_the_fallback_audit_record_and_the_legacy_record_both_still_read(
    tmp_path: Path,
) -> None:
    """The other two readers over the same file, each returning its live set."""
    path = _mixed_journal(tmp_path=tmp_path)

    exhaustion = importlib.import_module(f"{_PACKAGE}.{_EXHAUSTION_MODULE}")

    warnings = read_model_fallback_warnings(journal_path=path)
    exhaustions = exhaustion.live_provider_exhaustions(journal_path=path, now_iso=_WITHIN_EXPIRY)

    assert [entry.warning_id for entry in warnings.warnings] == ["acpwarn-live"]
    assert warnings.unobservable == ()
    assert [record.provider for record in exhaustions] == ["codex"]
