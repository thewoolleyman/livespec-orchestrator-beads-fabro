"""Projecting ACP fallback events into holds, warnings and the failure fact.

Binds the Dispatcher half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "Events and projection
are compatible, idempotent, and leak-free", together with Scenario 127's
"Projection is server-qualified, idempotent, and fail-closed for
unattended picking" and "Warning clearance is ordered and
generation-safe".

FOUR CONTROLS CARRY MOST OF THE WEIGHT, because each is a claim an
almost-correct implementation gets exactly backwards:

- RE-PROJECTING the same events must append NOTHING and must not move an
  existing hold's expiry. A dedupe written as "replace the record" passes
  a duplicate count and still refreshes the hold on every reconcile tick.
- RUN ABSENCE is a FAILURE, not a resolution. A forgotten run returns the
  cleanest possible empty answer, and reading it as a completed
  projection would clear the fact and resume unattended picking on a
  repository nobody read.
- A SUCCESSFUL FALLBACK must not clear the primary it fell back from,
  even when the run as a whole succeeded.
- An unknown `schema_version` is PRESERVED and surfaced, never dropped
  and never read on v1's field meanings.

Everything is HERMETIC: journals are built in `tmp_path`, every event is
a fixture dict, and nothing launches an adapter or reaches a factory.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NEW_MODULES = (
    "_acp_journal_records",
    "_acp_fallback_event_types",
    "_acp_fallback_events",
    "_acp_fallback_warning_records",
    "_acp_fallback_warning_ledger",
    "_acp_projection_failure",
    "_acp_event_projection",
)

_OCCURRED = "2026-09-12T12:00:00Z"
_LATER = "2026-09-12T12:05:00Z"
_EARLIER = "2026-09-12T11:55:00Z"
_WITHIN_EXPIRY = "2026-09-12T12:10:00Z"
_PRIMARY_GENERATION = "gen-primary-aaa"
_REPLACEMENT_GENERATION = "gen-primary-bbb"
_FULL_CHAIN = "chain-111"


def _modules() -> dict[str, Any]:
    """Import the slice's modules, proving each file exists first."""
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"
    return {name: importlib.import_module(f"{_PACKAGE}.{name}") for name in _NEW_MODULES}


class _Journal:
    """An in-memory append seam that also mirrors onto a real journal file."""

    def __init__(self, *, path: Path) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, object]) -> None:
        stamped = {"at": _OCCURRED, "invoker": "human:tester", **record}
        self.records.append(dict(stamped))
        with self.path.open("a", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(stamped, sort_keys=True) + "\n")

    def staged(self, *, stage: str) -> list[dict[str, Any]]:
        return [record for record in self.records if record.get("stage") == stage]


def _identity(*, index: int, key: str, domain: str = "codex") -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": domain,
    }


def _failover(
    *,
    event_id: str = "ev-1",
    node: str = "implement",
    occurred_at: str = _OCCURRED,
    scope: str = "availability-domain",
    to_index: int | None = 1,
    primary_generation: str = _PRIMARY_GENERATION,
    schema_version: int = 1,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "agent.acp.failover",
        "schema_version": schema_version,
        "event_id": event_id,
        "occurred_at": occurred_at,
        "node": node,
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(index=0, key="gpt-5-5"),
        "hold_key": "codex",
        "cause": "quota",
        "scope": scope,
        "primary_generation": primary_generation,
        "full_chain": _FULL_CHAIN,
        "attempted": ["gpt-5-5"],
        "skipped": [],
    }
    if to_index is not None:
        record["to"] = _identity(index=to_index, key="claude-haiku")
    return record


def _exhausted(*, event_id: str = "ev-exhausted", node: str = "review") -> dict[str, Any]:
    return {
        "type": "agent.acp.exhausted",
        "schema_version": 1,
        "event_id": event_id,
        "occurred_at": _OCCURRED,
        "node": node,
        "node_visit": 1,
        "engine_attempt": 2,
        "from": _identity(index=1, key="claude-haiku"),
        "hold_key": "codex",
        "cause": "model_unsupported",
        "scope": "candidate",
        "primary_generation": _PRIMARY_GENERATION,
        "full_chain": _FULL_CHAIN,
        "attempted": ["gpt-5-5", "claude-haiku"],
        "skipped": [],
    }


def _started(
    *,
    node: str = "implement",
    candidate_index: int = 0,
    occurred_at: str = _LATER,
    primary_generation: str = _PRIMARY_GENERATION,
    node_visit: int = 2,
) -> dict[str, Any]:
    return {
        "type": "agent.acp.started",
        "schema_version": 1,
        "node": node,
        "node_visit": node_visit,
        "candidate_index": candidate_index,
        "occurred_at": occurred_at,
        "primary_generation": primary_generation,
    }


def _target(
    *,
    nodes: dict[str, str] | None = None,
    succeeded: frozenset[str] = frozenset(),
    run_id: str = "01RUN",
) -> Any:
    projection = _modules()["_acp_event_projection"]
    return projection.AcpProjectionTarget(
        repo_name="livespec-orchestrator-beads-fabro",
        run_id=run_id,
        work_item_id="bd-ib-xtgwpz",
        factory_name="hp",
        factory_server_url="https://hp-xubuntu.perch-rudd.ts.net:32276",
        primary_generations={"implement": _PRIMARY_GENERATION} if nodes is None else nodes,
        succeeded_nodes=succeeded,
    )


def _journal(*, tmp_path: Path) -> _Journal:
    return _Journal(path=tmp_path / "fabro-dispatch-journal.jsonl")


def test_each_failover_and_exhausted_event_projects_one_versioned_hold_observation(
    tmp_path: Path,
) -> None:
    """Both projectable event types mint a hold keyed by the stable event id."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    holds = modules["_acp_hold_ledger"] = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    journal = _journal(tmp_path=tmp_path)
    result = projection.project_fetched_events(
        target=_target(),
        payload=[_failover(), _exhausted()],
        journal=journal,
        journal_path=journal.path,
    )
    assert result.holds == 2
    ledger = holds.read_acp_hold_ledger(journal_path=journal.path, now_iso=_WITHIN_EXPIRY)
    # The domain event keys on its hold key alone; the candidate-scoped
    # exhaustion keys on the exact identity pair of the candidate that failed.
    assert {hold.target for hold in ledger.holds} == {
        ("availability-domain", "codex", None),
        ("candidate", "codex", "claude-haiku"),
    }


def test_expiry_derives_from_occurrence_time_and_a_replay_never_moves_it(
    tmp_path: Path,
) -> None:
    """Re-projection is idempotent AND cannot refresh a stored expiry."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    holds = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    journal = _journal(tmp_path=tmp_path)
    first = projection.project_fetched_events(
        target=_target(), payload=[_failover()], journal=journal, journal_path=journal.path
    )
    before = holds.read_acp_hold_ledger(journal_path=journal.path, now_iso=_WITHIN_EXPIRY).holds
    # A replay of the SAME events, exactly as reconciliation performs it.
    second = projection.project_fetched_events(
        target=_target(), payload=[_failover()], journal=journal, journal_path=journal.path
    )
    after = holds.read_acp_hold_ledger(journal_path=journal.path, now_iso=_WITHIN_EXPIRY).holds
    assert (first.holds, second.holds) == (1, 0)
    assert len(after) == 1
    assert before[0].expires_at == after[0].expires_at == "2026-09-12T12:15:00Z"
    assert before[0].occurred_at == _OCCURRED


def test_an_unknown_event_schema_version_is_preserved_and_mints_nothing(
    tmp_path: Path,
) -> None:
    """A foreign version rides out as unobservable rather than as a hold."""
    modules = _modules()
    events = modules["_acp_fallback_events"]
    projection = modules["_acp_event_projection"]
    journal = _journal(tmp_path=tmp_path)
    scan = events.scan_acp_events(payload=[_failover(schema_version=2)])
    assert scan.events == ()
    # PRESERVED: the raw record survives with its foreign version intact.
    assert scan.unobservable[0]["schema_version"] == 2
    result = projection.project_fetched_events(
        target=_target(),
        payload=[_failover(schema_version=2)],
        journal=journal,
        journal_path=journal.path,
    )
    assert (result.holds, result.unobservable) == (0, 1)
    success = journal.staged(stage="acp-projection-succeeded")[0]
    assert success["unobservable_events"] == 1


def test_only_an_actually_executed_non_primary_candidate_yields_a_warning(
    tmp_path: Path,
) -> None:
    """Exhaustion and a transition back to candidate zero owe no warning."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    warnings = modules["_acp_fallback_warning_ledger"]
    journal = _journal(tmp_path=tmp_path)
    result = projection.project_fetched_events(
        target=_target(nodes={"implement": _PRIMARY_GENERATION, "review": _PRIMARY_GENERATION}),
        payload=[
            _failover(event_id="ev-executed", to_index=1),
            _failover(event_id="ev-primary-again", node="review", to_index=0),
            _failover(event_id="ev-no-target", node="review", to_index=None),
            _exhausted(event_id="ev-exhausted", node="review"),
        ],
        journal=journal,
        journal_path=journal.path,
    )
    assert result.warnings == 1
    live = warnings.read_model_fallback_warnings(journal_path=journal.path).warnings
    assert [warning.node for warning in live] == ["implement"]
    assert live[0].candidate_key == "claude-haiku"
    assert live[0].candidate_index == 1


def test_a_successful_fallback_run_does_not_clear_the_primary_hold_or_warning(
    tmp_path: Path,
) -> None:
    """Scenario 127: overall run success clears neither the hold nor the warning."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    warnings = modules["_acp_fallback_warning_ledger"]
    holds = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    journal = _journal(tmp_path=tmp_path)
    # The primary STARTED before the failover it then suffered, and the run
    # as a whole succeeded -- the exact shape that must still not clear.
    result = projection.project_fetched_events(
        target=_target(succeeded=frozenset({"implement"})),
        payload=[_started(occurred_at=_EARLIER, node_visit=1), _failover()],
        journal=journal,
        journal_path=journal.path,
    )
    assert (result.cleared, result.warnings) == (0, 1)
    assert warnings.read_model_fallback_warnings(journal_path=journal.path).warnings
    assert holds.read_acp_hold_ledger(journal_path=journal.path, now_iso=_WITHIN_EXPIRY).holds


def test_a_later_successful_primary_attempt_of_the_same_generation_clears_it(
    tmp_path: Path,
) -> None:
    """The clearance rule, in the one combination that satisfies all four claims."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    warnings = modules["_acp_fallback_warning_ledger"]
    journal = _journal(tmp_path=tmp_path)
    _ = projection.project_fetched_events(
        target=_target(), payload=[_failover()], journal=journal, journal_path=journal.path
    )
    assert warnings.read_model_fallback_warnings(journal_path=journal.path).warnings
    # A LATER visit whose primary started after the warning and succeeded.
    second = projection.project_fetched_events(
        target=_target(succeeded=frozenset({"implement"})),
        payload=[_started(occurred_at=_LATER)],
        journal=journal,
        journal_path=journal.path,
    )
    assert second.cleared == 1
    assert warnings.read_model_fallback_warnings(journal_path=journal.path).warnings == ()
    # APPEND-ONLY: the observation line is still there, retired by a later line.
    assert journal.staged(stage="acp-model-fallback-observed")
    assert journal.staged(stage="acp-model-fallback-cleared")


def test_a_primary_replacement_supersedes_while_a_fallback_only_edit_does_not(
    tmp_path: Path,
) -> None:
    """Which digest moved decides whether the warning is stranded or retired."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    warnings = modules["_acp_fallback_warning_ledger"]
    journal = _journal(tmp_path=tmp_path)
    _ = projection.project_fetched_events(
        target=_target(), payload=[_failover()], journal=journal, journal_path=journal.path
    )
    # A fallback-only edit: the full-chain digest moves, the primary does not.
    unchanged = projection.project_fetched_events(
        target=_target(nodes={"implement": _PRIMARY_GENERATION}),
        payload=[],
        journal=journal,
        journal_path=journal.path,
    )
    assert unchanged.superseded == 0
    assert warnings.read_model_fallback_warnings(journal_path=journal.path).warnings
    # A PRIMARY replacement: the generation the warning names no longer runs.
    replaced = projection.project_fetched_events(
        target=_target(nodes={"implement": _REPLACEMENT_GENERATION}),
        payload=[],
        journal=journal,
        journal_path=journal.path,
    )
    assert replaced.superseded == 1
    assert warnings.read_model_fallback_warnings(journal_path=journal.path).warnings == ()
    superseded = journal.staged(stage="acp-model-fallback-superseded")[0]
    assert superseded["current_primary_generation"] == _REPLACEMENT_GENERATION


def test_every_read_failure_arm_records_one_aggregating_per_node_fact(
    tmp_path: Path,
) -> None:
    """The four arms the clause enumerates, and their aggregation into one id."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    assert projection.classify_events_failure(exit_code=124, output="", payload=None) == (
        failure.REASON_TIMED_OUT
    )
    assert (
        projection.classify_events_failure(exit_code=1, output="run 01RUN not found", payload=None)
        == failure.REASON_RUN_NOT_FOUND
    )
    assert projection.classify_events_failure(exit_code=1, output="boom", payload=None) == (
        failure.REASON_FETCH_FAILED
    )
    assert projection.classify_events_failure(exit_code=0, output="", payload=None) == (
        failure.REASON_UNPARSEABLE
    )
    assert projection.classify_events_failure(exit_code=0, output="", payload=[]) is None
    journal = _journal(tmp_path=tmp_path)
    target = _target(nodes={"implement": _PRIMARY_GENERATION, "pr": _PRIMARY_GENERATION})
    for _attempt in range(2):
        outcome = projection.record_projection_failure(
            target=target, reason=failure.REASON_FETCH_FAILED, exit_code=1, journal=journal
        )
        assert outcome.read is False
    unresolved = failure.unresolved_projection_failures(journal_path=journal.path)
    # One fact per NODE, and repeats aggregate into the same id.
    assert [entry.fact_id for entry in unresolved] == [
        "hygiene:model-fallback-projection:livespec-orchestrator-beads-fabro:01RUN:implement",
        "hygiene:model-fallback-projection:livespec-orchestrator-beads-fabro:01RUN:pr",
    ]
    assert {entry.occurrences for entry in unresolved} == {2}
    assert "2 attempts" in unresolved[0].summary


def test_run_absence_is_a_failure_and_never_resolves_the_fact(tmp_path: Path) -> None:
    """A forgotten run's clean empty answer must not read as a projection."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    journal = _journal(tmp_path=tmp_path)
    _ = projection.record_projection_failure(
        target=_target(), reason=failure.REASON_FETCH_FAILED, exit_code=1, journal=journal
    )
    _ = projection.record_projection_failure(
        target=_target(), reason=failure.REASON_RUN_NOT_FOUND, exit_code=1, journal=journal
    )
    unresolved = failure.unresolved_projection_failures(journal_path=journal.path)
    assert len(unresolved) == 1
    assert unresolved[0].reason == failure.REASON_RUN_NOT_FOUND


def test_a_successful_projection_clears_the_fact_for_that_run_and_node(
    tmp_path: Path,
) -> None:
    """Only a read that actually succeeded retires the failure fact."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    journal = _journal(tmp_path=tmp_path)
    target = _target(nodes={"implement": _PRIMARY_GENERATION, "pr": _PRIMARY_GENERATION})
    _ = projection.record_projection_failure(
        target=target, reason=failure.REASON_TIMED_OUT, exit_code=124, journal=journal
    )
    assert len(failure.unresolved_projection_failures(journal_path=journal.path)) == 2
    _ = projection.project_fetched_events(
        target=target, payload=[], journal=journal, journal_path=journal.path
    )
    assert failure.unresolved_projection_failures(journal_path=journal.path) == ()


def test_an_unparseable_payload_records_a_failure_rather_than_an_empty_stream(
    tmp_path: Path,
) -> None:
    """A payload that is JSON but not an event array is UNREAD, not empty."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    events = modules["_acp_fallback_events"]
    assert isinstance(events.scan_acp_events(payload={"runs": []}), str)
    journal = _journal(tmp_path=tmp_path)
    result = projection.project_fetched_events(
        target=_target(), payload={"nope": 1}, journal=journal, journal_path=journal.path
    )
    assert result.reason == failure.REASON_UNPARSEABLE
    assert failure.unresolved_projection_failures(journal_path=journal.path)


def test_projection_records_carry_identities_and_digests_but_no_diagnostic(
    tmp_path: Path,
) -> None:
    """Leak-free: no command, env value, credential, prompt or raw error."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    journal = _journal(tmp_path=tmp_path)
    _ = projection.project_fetched_events(
        target=_target(), payload=[_failover()], journal=journal, journal_path=journal.path
    )
    _ = projection.record_projection_failure(
        target=_target(run_id="01OTHER"),
        reason=failure.REASON_FETCH_FAILED,
        exit_code=1,
        journal=journal,
    )
    forbidden = (
        "codex exec",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "--api-key",
        "Traceback",
        "sk-",
    )
    body = journal.path.read_text(encoding="utf-8")
    assert not any(token in body for token in forbidden)
    warning = journal.staged(stage="acp-model-fallback-observed")[0]
    # What it DOES carry: display name, machine keys, typed cause/scope, digests.
    assert warning["candidate_display_name"] == "display claude-haiku"
    assert warning["candidate_key"] == "claude-haiku"
    assert warning["cause"] == "quota"
    assert warning["primary_generation"] == _PRIMARY_GENERATION
    assert warning["full_chain"] == _FULL_CHAIN


def test_a_repository_with_no_fallback_enabled_node_projects_and_records_nothing(
    tmp_path: Path,
) -> None:
    """The additive guarantee: no enabled node means no fact and no write."""
    modules = _modules()
    projection = modules["_acp_event_projection"]
    failure = modules["_acp_projection_failure"]
    journal = _journal(tmp_path=tmp_path)
    empty = _target(nodes={})
    _ = projection.record_projection_failure(
        target=empty, reason=failure.REASON_FETCH_FAILED, exit_code=1, journal=journal
    )
    result = projection.project_fetched_events(
        target=empty, payload=[_failover()], journal=journal, journal_path=journal.path
    )
    # The events still project into holds, but no per-node fact is raised.
    assert result.nodes == ()
    assert journal.staged(stage="acp-projection-failure") == []
    assert journal.staged(stage="acp-projection-succeeded") == []
