"""The host-wide read reports which observations an operator clearance retired.

Binds the retirement half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "Observations, successful
availability confirmations, and operator clearances MUST each be recorded as a
factory-native record on the participating factory whose evidence they create
or retire ... so retirement is reconstructible from the same source as
observation", together with Scenario 116's operator act and Scenario 127's
host-visible half -- the sub-scenario where removing a repository-local journal
does not erase a host-visible hold.

THE CLAIM IS A JOIN ACROSS REPOSITORIES, so the fixtures are built so that an
implementation reading only its own journal cannot pass: the hold is derived
from ANOTHER repository's failed run, the clearance is a THIRD repository's
clearance run, and no journal is supplied to the read at all -- there is no
parameter one could arrive in.

THE CLEARANCE NAMES THE DERIVED OBSERVATION'S OWN ID, read off the evidence
rather than spelled, because that id is a digest of the evidence plus the scope
it lands on: a spelled constant would pass against a reader that retired
whatever ids it was handed, and would stop meaning anything the moment the
digest's inputs changed.

Everything is HERMETIC: the factory reads arrive through an injected reader, no
port is constructed, nothing launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import dataclasses
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_EVIDENCE_MODULE = "_acp_factory_hold_evidence"

_NOW = "2026-10-16T12:00:00Z"
# A run that started twenty minutes ago and ran for ten, so its failing attempt
# occurred ten minutes ago -- inside the fifteen-minute hold window.
_FAILED_STARTED_AT = "2026-10-16T11:40:00Z"
_FAILED_WALL_TIME_MS = 600_000
# The clearance run began five minutes ago, after that failure.
_CLEARED_STARTED_AT = "2026-10-16T11:55:00Z"
# And one that began fifty minutes ago, outside the window entirely.
_STALE_STARTED_AT = "2026-10-16T11:10:00Z"

_FAILED_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"
_CLEARANCE_RUN_ID = "01M4CLEARANCE000000000000Z"

_PEER_REPOSITORY = "livespec-console-beads-fabro"
_CLEARING_REPOSITORY = "livespec-overseer"

_FAILED_LABELS: dict[str, str] = {
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
        "hp": {"server": "https://hp.example.ts.net:32276"}
      }
    }
  }
}
"""

# MEASURED 2026-08-22 across the ten Codex ceiling refusals on hp.
_CEILING_CAUSE = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage"


def _evidence() -> Any:
    """Import the host-wide read, and prove it reports retired observations.

    The field is asserted BEFORE anything is read, because "which observations
    this read found retired" is the whole of what the clearance arm adds: a
    read that derived the clearance and then dropped it would be a read whose
    every other value is correct and whose peers still see the hold.
    """
    module = importlib.import_module(f"{_PACKAGE}.{_EVIDENCE_MODULE}")
    names = {one.name for one in dataclasses.fields(module.FactoryHoldEvidence)}
    assert "retired_observation_ids" in names, (
        f"{_EVIDENCE_MODULE}.FactoryHoldEvidence reports no retired observations yet; it has "
        f"{sorted(names)}"
    )
    return module


def _clearance_records() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_clearance_records")


def _rows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    port = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    return port.fabro_run_summaries_from_payload(payload=payload)


def _failed_row() -> dict[str, Any]:
    """One measured `fabro ps -a --json` row for a peer's provider-limit failure."""
    return {
        "run_id": _FAILED_RUN_ID,
        "status": {"kind": "failed"},
        "goal": "Work-item: bd-peer-1\n",
        "start_time": _FAILED_STARTED_AT,
        "wall_time_ms": _FAILED_WALL_TIME_MS,
        "labels": dict(_FAILED_LABELS),
    }


def _clearance_row(*, started_at: str = _CLEARED_STARTED_AT) -> dict[str, Any]:
    """One clearance run's row, labelled exactly as the writer labels it."""
    clearance_records = _clearance_records()
    return {
        "run_id": _CLEARANCE_RUN_ID,
        "status": {"kind": "succeeded"},
        "goal": "Record one operator ACP availability clearance.\n",
        "start_time": started_at,
        "wall_time_ms": 4_000,
        "labels": {
            "livespec.repository": _CLEARING_REPOSITORY,
            clearance_records.CLEARANCE_LABEL_KEY: clearance_records.CLEARANCE_LABEL_VALUE,
        },
    }


def _failed_payload() -> list[dict[str, Any]]:
    """One measured `fabro inspect --json` record whose `implement` node failed."""
    return [
        {
            "run_id": _FAILED_RUN_ID,
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
                            "causes": ["ACP protocol error", _CEILING_CAUSE],
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


def _clearance_payload(*, observation_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    """The clearance run's record, carrying the line the writer's script prints."""
    clearance_records = _clearance_records()
    clearance = clearance_records.AcpHoldClearance(
        scope="availability-domain",
        hold_key="codex",
        candidate_key=None,
        observation_ids=observation_ids,
        actor="human:maintainer",
        cleared_at="2026-10-16T11:55:00Z",
        reason="the account allowance reset",
    )
    return [
        {
            "run_id": _CLEARANCE_RUN_ID,
            "status": {"kind": "succeeded"},
            "stages": {
                "002-record@1": {
                    "handler": "script",
                    "state": "succeeded",
                    "output": clearance_records.clearance_outcome_text(clearance=clearance),
                }
            },
        }
    ]


@dataclass(kw_only=True)
class _Reader:
    """A factory run reader that records exactly which reads were spent."""

    rows: dict[str, tuple[Any, ...] | None] = field(default_factory=dict)
    payloads: dict[tuple[str, str], object | None] = field(default_factory=dict)
    inspected: list[tuple[str, str]] = field(default_factory=list)

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self.rows.get(factory, ())

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.inspected.append((factory, run_id))
        return self.payloads.get((factory, run_id))


def _repo(*, tmp_path: Path) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _derived_hold_id(*, tmp_path: Path) -> str:
    """The id the peer's failed attempt derives, read off the evidence itself."""
    module = _evidence()
    reader = _Reader(
        rows={"hp": _rows(payload=[_failed_row()])},
        payloads={("hp", _FAILED_RUN_ID): _failed_payload()},
    )
    evidence = module.factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso=_NOW
    )
    assert len(evidence.holds) == 1
    return str(evidence.holds[0].observation_id)


def test_a_clearance_run_retires_the_observation_it_names(tmp_path: Path) -> None:
    """A third repository's clearance reaches a hold a second one's run minted.

    The CONTROL is the same listing without the clearance row: without it a
    read that reported every derived id as retired would satisfy the positive
    assertion while retiring every hold on the host.
    """
    module = _evidence()
    repo = _repo(tmp_path=tmp_path)
    observation_id = _derived_hold_id(tmp_path=tmp_path)

    uncleared = module.factory_hold_evidence(
        repo=repo,
        reader=_Reader(
            rows={"hp": _rows(payload=[_failed_row()])},
            payloads={("hp", _FAILED_RUN_ID): _failed_payload()},
        ),
        now_iso=_NOW,
    )
    assert uncleared.retired_observation_ids == frozenset()

    cleared = module.factory_hold_evidence(
        repo=repo,
        reader=_Reader(
            rows={"hp": _rows(payload=[_failed_row(), _clearance_row()])},
            payloads={
                ("hp", _FAILED_RUN_ID): _failed_payload(),
                ("hp", _CLEARANCE_RUN_ID): _clearance_payload(observation_ids=(observation_id,)),
            },
        ),
        now_iso=_NOW,
    )
    assert cleared.retired_observation_ids == frozenset({observation_id})
    # The hold itself is still DERIVED -- the read reports what it found and
    # what a clearance retired; applying the two is the union's job.
    assert [hold.observation_id for hold in cleared.holds] == [observation_id]


def test_a_clearance_run_is_not_itself_an_attempt(tmp_path: Path) -> None:
    """It spends no allowance, so it neither observes a hold nor confirms one."""
    module = _evidence()
    reader = _Reader(
        rows={"hp": _rows(payload=[_clearance_row()])},
        payloads={
            ("hp", _CLEARANCE_RUN_ID): _clearance_payload(
                observation_ids=("acpobs-aaaaaaaaaaaaaaaaaaaaaaaa",)
            )
        },
    )

    evidence = module.factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso=_NOW
    )

    assert evidence.observations == ()
    assert evidence.successes == ()
    assert evidence.unobservable == ()
    assert evidence.retired_observation_ids == frozenset({"acpobs-aaaaaaaaaaaaaaaaaaaaaaaa"})


def test_a_clearance_older_than_the_hold_window_is_not_read_at_all(tmp_path: Path) -> None:
    """Its scan is bounded by the LISTING row, before a per-run read is spent.

    A clearance that began longer ago than the hold interval can only retire a
    record that has already expired on its own, so spending an `inspect` on it
    would cost one round trip per historical clearance on every admission
    evaluation -- the same bound the observation and confirmation arms take.
    """
    module = _evidence()
    reader = _Reader(
        rows={"hp": _rows(payload=[_clearance_row(started_at=_STALE_STARTED_AT)])},
        payloads={
            ("hp", _CLEARANCE_RUN_ID): _clearance_payload(
                observation_ids=("acpobs-aaaaaaaaaaaaaaaaaaaaaaaa",)
            )
        },
    )

    evidence = module.factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso=_NOW
    )

    assert reader.inspected == []
    assert evidence.retired_observation_ids == frozenset()


def test_a_clearance_run_recording_nothing_readable_retires_nothing(tmp_path: Path) -> None:
    """Retirement is the destructive direction, so an unreadable record stands."""
    module = _evidence()
    reader = _Reader(
        rows={"hp": _rows(payload=[_clearance_row()])},
        payloads={("hp", _CLEARANCE_RUN_ID): [{"run_id": _CLEARANCE_RUN_ID, "stages": {}}]},
    )

    evidence = module.factory_hold_evidence(
        repo=_repo(tmp_path=tmp_path), reader=reader, now_iso=_NOW
    )

    assert evidence.retired_observation_ids == frozenset()
