"""Host-wide ACP availability evidence, derived from factory-native run records.

Binds the host-wide half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -- "Holds are per provider domain
and discoverable host-wide from factory-native run records" -- together with
Scenario 127, "Ordered ACP fallback preserves primary resolution and failure
honesty, and re-dispatches past a held provider".

THE CLAIM UNDER TEST IS A JOIN ACROSS REPOSITORIES, so the controls are built
so that an implementation reading only its OWN evidence cannot pass them. Every
run row below is stamped with ANOTHER repository's name, and the only thing
connecting it to this repository's chain is the entitlement the factory itself
recorded on the run.

Everything is HERMETIC: the factory reads arrive through an injected reader,
no port is constructed, nothing launches an adapter and nothing reaches a
provider.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_factory_hold_evidence"
_RECORDS_MODULE = "_acp_factory_hold_records"

# What each module owns after the split, as the exact public surface. The
# RECORD concern is the leaf -- one derived attempt, its typed hold and its
# journal line -- and the EVIDENCE concern is the host-wide read that produces
# those attempts. The pairing mirrors `_acp_hold_records` / `_acp_hold_ledger`
# one level down, and the direction is what keeps it acyclic: the reader
# imports the record, never the other way round.
_RECORDS_SURFACE = (
    "AUDIT_REFERENCE_KEY",
    "FACTORY_EVIDENCE_KIND",
    "FACTORY_EVIDENCE_SOURCE",
    "PROVIDER_LIMIT_CAUSE",
    "FactoryHoldObservation",
    "attempt_expiry",
    "factory_hold_observation_record",
    "observation_hold",
)
_EVIDENCE_SURFACE = (
    "EMPTY_FACTORY_HOLD_EVIDENCE",
    "INSPECT_UNREADABLE",
    "LISTING_UNREADABLE",
    "OCCURRENCE_UNREADABLE",
    "FactoryHoldEvidence",
    "FactoryRunReader",
    "factory_hold_evidence",
)

_NOW = "2026-10-16T12:00:00Z"

# A run that STARTED twenty minutes before `now` and ran for ten, so its
# failing attempt occurred at 11:50:00Z -- ten minutes ago, which is inside
# the fifteen-minute hold window and therefore still live.
_STARTED_AT = "2026-10-16T11:40:00Z"
_WALL_TIME_MS = 600_000
_OCCURRED_AT = "2026-10-16T11:50:00Z"

# That occurrence advanced by the ratified fifteen-minute hold interval. It is
# spelled rather than computed so the expected value cannot be derived by the
# same arithmetic the implementation uses.
_EXPIRES_AT = "2026-10-16T12:05:00Z"

_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"

# ANOTHER repository's run. The whole point of the clause is that this
# repository learns of the outage without having failed a run of its own.
_PEER_REPOSITORY = "livespec-console-beads-fabro"

_LABELS: dict[str, str] = {
    "livespec.repository": _PEER_REPOSITORY,
    "livespec.dispatch.factory": "hp",
    "livespec.acp.implement.availability": "codex",
    "livespec.acp.implement.candidate": "primary",
}

_FACTORIES_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"},
        "vps": {"server": "https://vps.example.ts.net:32276"}
      }
    }
  }
}
"""

_CHAIN_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"},
        "vps": {"server": "https://vps.example.ts.net:32276"}
      },
      "acp_nodes": {
        "implement": {
          "display_name": "Primary",
          "candidate_key": "primary",
          "availability_key": "codex",
          "command": "adapter-primary",
          "fallbacks": [
            {
              "display_name": "Fallback",
              "candidate_key": "fallback",
              "availability_key": "anthropic",
              "command": "adapter-fallback"
            }
          ]
        }
      }
    }
  }
}
"""

# A typed v1 observation the REPOSITORY'S OWN journal carries, on the
# fallback's allowance. Its presence is what makes the journal observable in
# the reconstruction case below: with it, both candidates are skipped.
_JOURNALLED_FALLBACK_HOLD: dict[str, Any] = {
    "stage": "acp-availability-observed",
    "schema_version": 1,
    "observation_id": "acpobs-journalled-fallback",
    "scope": "availability-domain",
    "hold_key": "anthropic",
    "candidate_key": None,
    "cause": "quota",
    "evidence_kind": "acp-failover-event",
    "evidence_id": "evt-1",
    "occurred_at": _OCCURRED_AT,
    "expires_at": _EXPIRES_AT,
    "work_item_id": "bd-own-1",
    "node": "implement",
}

_CHAIN_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_CHAIN_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""


def _module() -> Any:
    """Import the slice's module, proving its file exists first."""
    assert (_COMMANDS / f"{_MODULE}.py").is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _records() -> Any:
    """Import the derived-record leaf, proving its file exists first."""
    path = _COMMANDS / f"{_RECORDS_MODULE}.py"
    assert path.is_file(), f"{_RECORDS_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_RECORDS_MODULE}")


def _repo(*, tmp_path: Path) -> Path:
    """A repository declaring two participating factories."""
    (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _chain_repo(*, tmp_path: Path) -> Path:
    """The same two factories, plus an `implement` chain the evidence can cover.

    Candidate zero's `availability_key` is the one the peer repository's run
    row records as spent; candidate one's is not. So the chain stays viable
    and the skip is attributable to exactly one hold.
    """
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_CHAIN_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_CHAIN_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_CHAIN_CONFIG, encoding="utf-8")
    return tmp_path


def _candidate_keys(*, verdict: Any) -> list[str | None]:
    """The `implement` node's surviving candidates, in configured order."""
    node = verdict.node_preflight(node="implement")
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in node.candidates
    ]


def _rows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Run rows as the port's own projection of a `fabro ps -a --json` payload."""
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    return records.fabro_run_summaries_from_payload(payload=payload)


def _row_payload(
    *,
    run_id: str = _RUN_ID,
    status: str = "failed",
    start_time: str | None = _STARTED_AT,
    wall_time_ms: int | None = _WALL_TIME_MS,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One measured `fabro ps -a --json` row, in the engine's own shape."""
    record: dict[str, Any] = {
        "run_id": run_id,
        "status": {"kind": status},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
        "labels": dict(_LABELS if labels is None else labels),
    }
    if start_time is not None:
        record["start_time"] = start_time
    if wall_time_ms is not None:
        record["wall_time_ms"] = wall_time_ms
    return record


def _inspect_payload(*, cause: str) -> list[dict[str, Any]]:
    """One measured `fabro inspect --json` record whose `implement` node failed."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "checkpoint": {
                "current_node": "needs_human",
                "completed_nodes": ["setup", "dod_gate", "implement"],
                "node_outcomes": {
                    "implement": {
                        "status": "failed",
                        "failure": {
                            "category": "transient_infra",
                            "signature": "implement|transient_infra|acp turn failed",
                            "causes": ["ACP protocol error", cause],
                        },
                    },
                    "needs_human": {
                        "status": "failed",
                        "failure": {
                            "category": "deterministic",
                            "signature": "needs_human|deterministic|script failed",
                            "causes": ["stage needs_human failed with no outgoing fail edge"],
                        },
                    },
                },
            },
        }
    ]


# MEASURED 2026-08-22 across the ten Codex ceiling refusals on hp.
_CEILING_CAUSE = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage"
# An ordinary transport fault, which is NOT an availability cause.
_TRANSPORT_CAUSE = "connection reset by peer"


@dataclass(kw_only=True)
class _Reader:
    """A factory run reader that records exactly which reads were spent."""

    rows: dict[str, tuple[Any, ...] | None] = field(default_factory=dict)
    payloads: dict[tuple[str, str], object | None] = field(default_factory=dict)
    listed: list[str] = field(default_factory=list)
    inspected: list[tuple[str, str]] = field(default_factory=list)

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        self.listed.append(factory)
        return self.rows.get(factory, ())

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.inspected.append((factory, run_id))
        return self.payloads.get((factory, run_id))


def test_every_declared_factory_is_read_and_a_failed_attempt_is_one_identified_observation(
    tmp_path: Path,
) -> None:
    """The six identifiers the clause enumerates, read off the factory's own records.

    "Each recorded attempt MUST identify its resolved factory, repository, run,
    node attempt, candidate entitlement, occurrence time, and typed
    availability outcome." The run belongs to a DIFFERENT repository, and
    nothing in this repository's journal mentions it.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert reader.listed == ["hp", "vps"]
    assert len(evidence.observations) == 1
    observation = evidence.observations[0]
    assert observation.factory == "hp"
    assert observation.repository == _PEER_REPOSITORY
    assert observation.run_id == _RUN_ID
    assert observation.node_attempt == "implement"
    assert observation.availability_key == "codex"
    assert observation.candidate_key == "primary"
    assert observation.occurred_at == _OCCURRED_AT
    assert observation.cause == _records().PROVIDER_LIMIT_CAUSE


def test_a_failure_that_is_not_an_eligible_availability_cause_yields_no_observation(
    tmp_path: Path,
) -> None:
    """An ordinary transport fault is a failed run, and no evidence about a provider."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_TRANSPORT_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert evidence.unobservable == ()


def test_a_succeeded_run_is_never_inspected(tmp_path: Path) -> None:
    """The scan costs one inspect per FAILED row, never one per listed row."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(rows={"hp": _rows(payload=[_row_payload(status="succeeded")])})

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert reader.inspected == []


def test_a_failure_older_than_the_longest_hold_window_is_not_inspected(tmp_path: Path) -> None:
    """The bound is applied from the ROW, before any per-run read is spent.

    A factory serving this fleet listed 1626 rows on 2026-10-12, so a scan that
    inspected every failed row would spend a round trip per historical failure
    to re-derive a hold that expired hours ago.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(start_time="2026-10-16T09:00:00Z")])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert reader.inspected == []


def test_an_unreadable_listing_is_surfaced_rather_than_read_as_an_empty_hold_set(
    tmp_path: Path,
) -> None:
    """ "An unreadable or incomplete evidence source is unavailable, not an empty hold set."

    The surviving factory's own evidence still contributes, which is the
    clause's "It MAY continue with candidates whose availability evidence is
    independently complete".
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": None, "vps": _rows(payload=[_row_payload()])},
        payloads={("vps", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert [observation.factory for observation in evidence.observations] == ["vps"]
    assert [entry.get("factory") for entry in evidence.unobservable] == ["hp"]
    assert evidence.unobservable[0]["reason"] == module.LISTING_UNREADABLE


def test_an_unreadable_run_record_is_surfaced_rather_than_passed_over(tmp_path: Path) -> None:
    """A failed row inside the window whose `inspect` cannot be read is unavailable.

    Distinguished from the ineligible-cause case above by the SURFACE, not by
    the observation count: both derive nothing, and only one of them is a
    failure to measure.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(rows={"hp": _rows(payload=[_row_payload()])})

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert reader.inspected == [("hp", _RUN_ID)]
    assert dict(evidence.unobservable[0]) == {
        "factory": "hp",
        "run_id": _RUN_ID,
        "reason": module.INSPECT_UNREADABLE,
    }


@pytest.mark.parametrize(
    "row",
    [
        pytest.param({"start_time": None}, id="no-start-time"),
        pytest.param({"wall_time_ms": None}, id="no-wall-time"),
        pytest.param({"start_time": "not-an-instant"}, id="unreadable-start-time"),
    ],
)
def test_a_row_that_cannot_date_its_attempt_is_unobservable_not_dated_from_its_start(
    tmp_path: Path, row: dict[str, Any]
) -> None:
    """The judgement call this module's docstring names, asserted in all three arms.

    Dating the attempt from the run's START would make every hold a long run
    could mint be born expired, so the scan would report a clean empty answer
    on exactly the outage it exists to catch. The `inspect` is not spent
    either: an attempt nobody can date cannot be placed inside the window.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(**row)])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert reader.inspected == []
    assert evidence.unobservable[0]["reason"] == module.OCCURRENCE_UNREADABLE


def test_a_petri_era_subsecond_instant_still_dates_its_attempt(tmp_path: Path) -> None:
    """The Petri-era build stamps nine fractional digits; no stdlib parser takes them.

    Measured on v0.378.0-nightly.0: `2026-10-08T12:34:14.182000000Z`. A reader
    that handed that to the hold parser unchanged would report EVERY row on
    that engine as undatable, which looks exactly like a factory holding no
    failures.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(start_time="2026-10-16T11:40:00.182000000Z")])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert [observation.occurred_at for observation in evidence.observations] == [_OCCURRED_AT]


def test_an_unreadable_clock_keeps_a_failed_row_inside_the_window(tmp_path: Path) -> None:
    """A caller's malformed clock must not silently drop live evidence.

    The expensive direction is dropping a hold and sending work at a live
    outage, so an unreadable `now` costs one `inspect` rather than an answer.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(start_time="2020-01-01T00:00:00Z")])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso="not-an-instant")

    assert [observation.run_id for observation in evidence.observations] == [_RUN_ID]


def test_a_failing_node_the_run_recorded_no_entitlement_for_derives_nothing(
    tmp_path: Path,
) -> None:
    """An identity-less adapter keeps the conservative v107 posture.

    There is no entitlement a typed record could be scoped by, and inventing
    one would name an allowance nobody declared. It is NOT surfaced as
    unobservable: the run record was read in full, and what it says is that
    this dispatch resolved no identity.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    unlabelled = {"livespec.repository": _PEER_REPOSITORY}
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(labels=unlabelled)])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert evidence.unobservable == ()


def test_an_observation_stands_for_a_domain_hold_on_the_spent_allowance(tmp_path: Path) -> None:
    """The entitlement that ran identifies the attempt; the ALLOWANCE is what is held.

    Scenario 127: "Then it records a domain hold on that candidate's
    availability key". A candidate-scoped record would leave every sibling on
    the same provider dispatching into the same refusal, which is why the
    built-in quota signatures are domain-scoped without exception -- and the
    hold parser refuses a domain record that names a candidate key at all.
    """
    module = _module()
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert len(evidence.holds) == 1
    hold = evidence.holds[0]
    assert hold.scope == classifier.DOMAIN_SCOPE
    assert hold.hold_key == "codex"
    assert hold.candidate_key is None
    assert hold.cause == _records().PROVIDER_LIMIT_CAUSE
    assert hold.occurred_at == _OCCURRED_AT
    # The id digests the FACTORY's own record, so two Dispatchers deriving one
    # attempt mint one id rather than two records of the same outage.
    assert _records().observation_hold(observation=evidence.observations[0]) == hold


def test_a_peer_repositorys_recorded_outage_skips_this_repositorys_covered_candidate(
    tmp_path: Path,
) -> None:
    """The clause's whole promise, through the verdict every consumer reads.

    "an observation made by any repository's run on a participating factory is
    visible to every repository that dispatches to it." Nothing in this
    repository's journal mentions the run, and the journal path is `None`.
    """
    preflight = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    repo = _chain_repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    verdict = preflight.resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW, factory_runs=reader
    )

    assert verdict.viable is True
    assert _candidate_keys(verdict=verdict) == ["fallback"]
    assert [hold.hold_key for hold in verdict.holds] == ["codex"]


def test_the_same_repository_with_no_factory_evidence_keeps_every_candidate(
    tmp_path: Path,
) -> None:
    """The control that makes the case above able to fail for the right reason.

    Without it, a preflight that dropped the primary for any other reason --
    an unreadable adapter, a mis-ordered chain -- would satisfy the skip
    assertion while reading no factory evidence at all.
    """
    preflight = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    repo = _chain_repo(tmp_path=tmp_path)

    verdict = preflight.resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW)

    assert _candidate_keys(verdict=verdict) == ["primary", "fallback"]
    assert verdict.holds == ()


def test_an_unreadable_factory_listing_rides_the_verdict_as_unobservable(
    tmp_path: Path,
) -> None:
    """An evidence source that could not be read is carried, never interpreted.

    The verdict stays VIABLE, which is the clause's "It MAY continue with
    candidates whose availability evidence is independently complete" -- what
    it must not do is report the unread factory as having held nothing.
    """
    module = _module()
    preflight = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    repo = _chain_repo(tmp_path=tmp_path)
    reader = _Reader(rows={"hp": None, "vps": None})

    verdict = preflight.resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW, factory_runs=reader
    )

    assert verdict.viable is True
    assert [entry["reason"] for entry in verdict.unobservable] == [
        module.LISTING_UNREADABLE,
        module.LISTING_UNREADABLE,
    ]


def test_a_sparse_row_reports_no_repository_rather_than_a_derived_one(tmp_path: Path) -> None:
    """`omitempty` sparseness is the engine's convention; an absent label is absent."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    entitlement_only = {
        "livespec.acp.implement.availability": "codex",
        "livespec.acp.implement.candidate": "primary",
    }
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload(labels=entitlement_only)])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert [observation.repository for observation in evidence.observations] == [None]


def test_a_run_record_carrying_no_terminal_evidence_names_no_node(tmp_path: Path) -> None:
    """A payload with no needs-human checkpoint establishes no failing node.

    The entitlement labels are present and well-formed, so this case fails for
    exactly one reason: nothing in the record says WHICH node's attempt spent
    the allowance, and a hold scoped to a guess is worse than none.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={
            ("hp", _RUN_ID): [
                {
                    "run_id": _RUN_ID,
                    "status": {"kind": "failed"},
                    "failure": {"category": "transient_infra", "causes": [_CEILING_CAUSE]},
                }
            ]
        },
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert evidence.observations == ()
    assert evidence.unobservable == ()


def test_hold_expiry_is_computed_from_the_failing_attempts_occurrence_time(
    tmp_path: Path,
) -> None:
    """ "Expiry is computed from occurrence time and never from ingestion."

    The attempt occurred at 11:50:00Z and the bounded interval is fifteen
    minutes, so the record stands until 12:05:00Z -- read off the ATTEMPT,
    not off the 12:00:00Z instant the derivation was taken at.
    """
    module = _module()
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    assert timedelta(minutes=15) == records.HOLD_INTERVAL
    assert evidence.observations[0].expires_at == _EXPIRES_AT
    assert evidence.holds[0].occurred_at == _OCCURRED_AT
    assert evidence.holds[0].expires_at == _EXPIRES_AT


def test_re_deriving_the_same_attempt_later_does_not_push_its_expiry_forward(
    tmp_path: Path,
) -> None:
    """Re-derivation is a replay, and a replay must not refresh a hold.

    This is the host-wide form of the property `hold_observation_record`
    holds by taking no clock: the evidence here is re-read from the factory
    on EVERY admission evaluation, so an expiry computed from the reading
    would make a single four-minute outage stand for as long as anyone kept
    looking at it.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    first = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)
    later = module.factory_hold_evidence(repo=repo, reader=reader, now_iso="2026-10-16T12:04:00Z")

    assert first.holds == later.holds
    assert later.holds[0].expires_at == _EXPIRES_AT


def test_an_unreadable_occurrence_is_carried_through_rather_than_given_a_bound() -> None:
    """An instant nobody can read is not one fifteen minutes can be added to.

    Unreachable through `factory_hold_evidence`, which formats every
    `occurred_at` from an instant it has already parsed -- but `attempt_expiry`
    is the one place the bound is computed, and what it must NOT do is invent
    one. Carrying the unreadable text through leaves the record's two instants
    saying the same unreadable thing; substituting a computed instant would
    date the record from the READING, which is exactly what the clause's
    "never from ingestion" forbids.

    Note what this case does NOT claim: `hold_expired` cannot read such a
    record either, so it reports the hold as standing. That is why no
    derivation here can produce one, and why the arm exists for a hand-built
    value rather than as a safety net.
    """
    observation = _records().FactoryHoldObservation(
        factory="hp",
        repository=_PEER_REPOSITORY,
        run_id=_RUN_ID,
        node_attempt="implement",
        availability_key="codex",
        candidate_key="primary",
        cause=_records().PROVIDER_LIMIT_CAUSE,
        occurred_at="not-an-instant",
    )

    assert _records().attempt_expiry(occurred_at="not-an-instant") == "not-an-instant"
    assert observation.expires_at == "not-an-instant"
    assert _records().observation_hold(observation=observation).expires_at == "not-an-instant"


def test_derived_holds_are_reconstructed_identically_once_the_journal_is_removed(
    tmp_path: Path,
) -> None:
    """ "Hold observations ... MUST remain reconstructible after any repository-local
    dispatch journal is removed."

    The journal here carries a typed record of its own, on the FALLBACK's
    allowance, so its presence is observable: with it, both candidates are
    skipped and the chain is exhausted. Removing it must take only that
    record away -- the factory-derived hold on the primary's allowance is
    byte-identical across the two reads, and still skips the primary.

    This is a CONTROL, not a claim about new code: the derivation takes no
    journal parameter at all, so the property holds structurally and this
    case passed the moment the derivation existed. What it guards is the
    UNION -- a merge that deduplicated against the journal, or that read the
    journal first and short-circuited, would fail here while satisfying every
    other case in this module.
    """
    preflight = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    repo = _chain_repo(tmp_path=tmp_path)
    journal = repo / "journal.jsonl"
    journal.write_text(json.dumps(_JOURNALLED_FALLBACK_HOLD) + "\n", encoding="utf-8")
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )

    with_journal = preflight.resolve_acp_preflight(
        repo=repo, journal_path=journal, now_iso=_NOW, factory_runs=reader
    )
    journal.unlink()
    without_journal = preflight.resolve_acp_preflight(
        repo=repo, journal_path=journal, now_iso=_NOW, factory_runs=reader
    )

    assert with_journal.viable is False
    assert _candidate_keys(verdict=with_journal) == []
    assert without_journal.viable is True
    assert _candidate_keys(verdict=without_journal) == ["fallback"]
    derived = [hold for hold in with_journal.holds if hold.hold_key == "codex"]
    assert derived == list(without_journal.holds)


def test_a_journaled_derived_record_carries_its_factory_run_as_the_audit_reference(
    tmp_path: Path,
) -> None:
    """ "Dispatch journals MAY record audit references but MUST NOT be the sole
    authority for holds."

    The record is an ordinary conformant v1 observation -- it reads back
    through `parse_hold_record` to the very hold the evidence stands for --
    PLUS the factory run it was derived from, so a reader of the journal is
    pointed at the authority rather than left holding the only copy.
    """
    module = _module()
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    repo = _repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_row_payload()])},
        payloads={("hp", _RUN_ID): _inspect_payload(cause=_CEILING_CAUSE)},
    )
    evidence = module.factory_hold_evidence(repo=repo, reader=reader, now_iso=_NOW)

    record = _records().factory_hold_observation_record(
        observation=evidence.observations[0], work_item_id="bd-ib-hyuqv6"
    )

    assert isinstance(record, dict)
    assert record[_records().AUDIT_REFERENCE_KEY] == f"hp:{_RUN_ID}:implement"
    assert records.parse_hold_record(record=record) == evidence.holds[0]


def test_a_record_whose_observation_cannot_be_dated_refuses_rather_than_appending() -> None:
    """The hold writer's own refusal is returned, not swallowed into a record.

    An appended line whose occurrence nobody can read is an audit reference to
    nothing: the hold it claims to mirror cannot be re-derived from it, which
    is the one property the journal copy exists to preserve.
    """
    observation = _records().FactoryHoldObservation(
        factory="hp",
        repository=_PEER_REPOSITORY,
        run_id=_RUN_ID,
        node_attempt="implement",
        availability_key="codex",
        candidate_key="primary",
        cause=_records().PROVIDER_LIMIT_CAUSE,
        occurred_at="not-an-instant",
    )

    refusal = _records().factory_hold_observation_record(
        observation=observation, work_item_id="bd-ib-hyuqv6"
    )

    assert isinstance(refusal, str)
    assert "not-an-instant" in refusal


def test_the_derived_record_concern_is_its_own_module_beneath_the_host_wide_read() -> None:
    """The two concerns, and the direction of the one edge between them.

    `_acp_factory_hold_records` owns ONE derived attempt -- its identity, its
    bounded expiry, the typed hold it stands for and the journal line that
    audits it -- and nothing about reading a factory. `_acp_factory_hold_
    evidence` owns the host-wide read that produces those attempts. The
    reader imports the record; the record imports no reader, which is what
    keeps the pair acyclic and what lets every record decision be exercised
    without a factory at all.

    The surfaces are asserted as EXACT sets rather than as membership: a
    split that left the moved names re-exported from their old home would
    satisfy every other case in this module while the file was no smaller.
    """
    evidence = _module()
    records = _records()

    assert tuple(records.__all__) == _RECORDS_SURFACE
    assert tuple(evidence.__all__) == _EVIDENCE_SURFACE
    # The reader genuinely USES three of the moved names, so it imports them
    # back; what it must not do is advertise them as its own.
    assert evidence.factory_hold_evidence.__module__.endswith(_MODULE)
    assert records.observation_hold.__module__.endswith(_RECORDS_MODULE)
    assert records.FactoryHoldObservation.__module__.endswith(_RECORDS_MODULE)
