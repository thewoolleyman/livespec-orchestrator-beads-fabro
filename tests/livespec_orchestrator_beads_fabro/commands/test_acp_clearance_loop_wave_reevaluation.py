"""After an operator clearance, the next loop-wave evaluation is not deferred.

Binds the half of `SPECIFICATION/contracts.md` section "Factory-configurable
ACP fallback priority" that makes a recorded clearance ACT: "Observations,
successful availability confirmations, and operator clearances MUST each be
recorded as a factory-native record on the participating factory whose evidence
they create or retire ... so retirement is reconstructible from the same source
as observation", read together with that section's Per-node selection
scheduling rule -- "The scheduled evaluation falls at the earliest expiry among
the holds that empty a chain, and otherwise after
`dispatcher.credential_reprobe_interval_seconds`; no human valve is the remedy
for that wait." Scenario 116 is the operator act, Scenario 60 the admission
refusal it lifts, and Scenario 127 the host-wide chain it lifts it on.

THE BEFORE READING IS THE CONTROL AND IT IS THE POINT OF THE FILE. Each case
below takes TWO evaluations at the SAME instant over the SAME configuration,
differing only in whether the factory carries the clearance record -- so the
"before" reading establishes that a wait WAS owed and names the instant it was
scheduled for, and the "after" reading establishes that the next evaluation
does not wait for it. Without the before reading, an implementation that
scheduled no wait at all would satisfy every assertion here.

THE WAVE'S OWN GATE IS READ, not only the wait. `dispatch_loop_wave` resolves
this very verdict and hands it to `await_usable_credential`, which is the one
thing in a wave that can HOLD it; `credential_reprobe_wait_applies` is that
gate's own predicate, so reading it is reading whether the wave would park.
A test that read the scheduled instant alone would pass against a build whose
wave still held for the cadence.

THE HOLD AND THE CLEARANCE BOTH BELONG TO OTHER REPOSITORIES, and no journal is
supplied to any evaluation: the whole claim is that this repository's next wave
observes an outage and a clearance it had no part in.

Everything is HERMETIC: configuration and the workflow graph live in
`tmp_path`, the factory reads arrive through an injected reader, no credential
probe and no headroom policy are supplied, and nothing reaches a provider.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T12:00:00Z"
# The peer run started twenty minutes ago and ran for ten, so its failing
# attempt occurred at 11:50:00Z -- inside the fifteen-minute hold window, and
# therefore expiring at 12:05:00Z, which is the instant a wait is scheduled for.
_FAILED_STARTED_AT = "2026-10-16T11:40:00Z"
_FAILED_WALL_TIME_MS = 600_000
_EXPIRES_AT = "2026-10-16T12:05:00Z"
# The clearance run began five minutes ago, after that failure.
_CLEARED_STARTED_AT = "2026-10-16T11:55:00Z"

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

# ONE `implement` chain whose primary and fallback spend the SAME account
# domain, which is the ordinary shape: a domain hold covers every sibling on
# the provider, so one observation empties the chain while the chain still
# DECLARES a fallback -- the combination the wave's own gate needs, since it
# holds unconditionally for a repository declaring none.
_CHAIN_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"}
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
              "availability_key": "codex",
              "command": "adapter-fallback"
            }
          ]
        }
      }
    }
  }
}
"""

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

# MEASURED 2026-08-22 across the ten Codex ceiling refusals on hp.
_CEILING_CAUSE = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage"


def _preflight() -> Any:
    return importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")


def _clearance_records() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_clearance_records")


def _rows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    port = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    return port.fabro_run_summaries_from_payload(payload=payload)


def _repo(*, tmp_path: Path) -> Path:
    """A repository declaring one factory and one fallback-enabled chain."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_CHAIN_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_CHAIN_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_CHAIN_CONFIG, encoding="utf-8")
    return tmp_path


def _failed_row() -> dict[str, Any]:
    return {
        "run_id": _FAILED_RUN_ID,
        "status": {"kind": "failed"},
        "goal": "Work-item: bd-peer-1\n",
        "start_time": _FAILED_STARTED_AT,
        "wall_time_ms": _FAILED_WALL_TIME_MS,
        "labels": dict(_FAILED_LABELS),
    }


def _clearance_row() -> dict[str, Any]:
    records = _clearance_records()
    return {
        "run_id": _CLEARANCE_RUN_ID,
        "status": {"kind": "succeeded"},
        "goal": "Record one operator ACP availability clearance.\n",
        "start_time": _CLEARED_STARTED_AT,
        "wall_time_ms": 4_000,
        "labels": {
            "livespec.repository": _CLEARING_REPOSITORY,
            records.CLEARANCE_LABEL_KEY: records.CLEARANCE_LABEL_VALUE,
        },
    }


def _failed_payload() -> list[dict[str, Any]]:
    return [
        {
            "run_id": _FAILED_RUN_ID,
            "status": {"kind": "failed"},
            "checkpoint": {
                "current_node": "needs_human",
                "completed_nodes": ["setup", "implement"],
                "node_outcomes": {
                    "implement": {
                        "status": "failed",
                        "failure": {
                            "category": "transient_infra",
                            "signature": "implement|transient_infra|acp turn failed",
                            "causes": ["ACP protocol error", _CEILING_CAUSE],
                        },
                    }
                },
            },
        }
    ]


def _clearance_payload(*, observation_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    records = _clearance_records()
    clearance = records.AcpHoldClearance(
        scope="availability-domain",
        hold_key="codex",
        candidate_key=None,
        observation_ids=observation_ids,
        actor="human:maintainer",
        cleared_at=_CLEARED_STARTED_AT,
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
                    "output": records.clearance_outcome_text(clearance=clearance),
                }
            },
        }
    ]


@dataclass(kw_only=True)
class _Reader:
    rows: dict[str, tuple[Any, ...] | None] = field(default_factory=dict)
    payloads: dict[tuple[str, str], object | None] = field(default_factory=dict)

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self.rows.get(factory, ())

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self.payloads.get((factory, run_id))


def _held_reader() -> _Reader:
    """The factory as it stands BEFORE the operator clears anything."""
    return _Reader(
        rows={"hp": _rows(payload=[_failed_row()])},
        payloads={("hp", _FAILED_RUN_ID): _failed_payload()},
    )


def _cleared_reader(*, observation_ids: tuple[str, ...]) -> _Reader:
    """The same factory once the clearance record stands beside the failure."""
    return _Reader(
        rows={"hp": _rows(payload=[_failed_row(), _clearance_row()])},
        payloads={
            ("hp", _FAILED_RUN_ID): _failed_payload(),
            ("hp", _CLEARANCE_RUN_ID): _clearance_payload(observation_ids=observation_ids),
        },
    )


def _verdict(*, repo: Path, reader: _Reader) -> Any:
    """One loop-wave ACP evaluation: no journal, no probe, no headroom policy."""
    return _preflight().resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW, factory_runs=reader
    )


def test_the_clearance_lifts_the_wait_the_previous_evaluation_scheduled(
    tmp_path: Path,
) -> None:
    """A wait WAS owed at this instant, and the next evaluation does not take it.

    The two readings are taken at ONE `now`, so the difference cannot be the
    clock: the earlier evaluation schedules the hold's own expiry and the later
    one, reading the clearance the operator recorded in between, schedules
    nothing at all.
    """
    module = _preflight()
    repo = _repo(tmp_path=tmp_path)

    held = _verdict(repo=repo, reader=_held_reader())
    assert held.fallback_enabled
    assert not held.viable
    scheduled = module.resolve_availability_wait(repo=repo, verdict=held, now_iso=_NOW)
    assert scheduled is not None
    assert scheduled.reevaluate_at == _EXPIRES_AT
    assert scheduled.node == "implement"

    cleared = _verdict(
        repo=repo,
        reader=_cleared_reader(observation_ids=tuple(hold.observation_id for hold in held.holds)),
    )

    assert cleared.viable
    assert cleared.holds == ()
    assert module.resolve_availability_wait(repo=repo, verdict=cleared, now_iso=_NOW) is None


def test_the_loop_wave_would_hold_before_the_clearance_and_not_after(
    tmp_path: Path,
) -> None:
    """The wave's own gate, which is the one thing in a wave that can park it.

    `dispatch_loop_wave` resolves this verdict and hands it to
    `await_usable_credential`; this predicate is what that wait reads to decide
    whether it may hold the wave at all.
    """
    module = _preflight()
    repo = _repo(tmp_path=tmp_path)

    held = _verdict(repo=repo, reader=_held_reader())
    assert module.credential_reprobe_wait_applies(verdict=held)

    cleared = _verdict(
        repo=repo,
        reader=_cleared_reader(observation_ids=tuple(hold.observation_id for hold in held.holds)),
    )

    assert not module.credential_reprobe_wait_applies(verdict=cleared)


def test_a_clearance_naming_another_observation_leaves_this_wait_standing(
    tmp_path: Path,
) -> None:
    """The retirement is EXACT, so a clearance of something else changes nothing.

    Without this case an implementation that emptied every chain on sight of
    any clearance record would satisfy both cases above -- and would send work
    at a live outage the moment any repository on the host cleared anything.
    """
    module = _preflight()
    repo = _repo(tmp_path=tmp_path)

    cleared = _verdict(
        repo=repo,
        reader=_cleared_reader(observation_ids=("acpobs-somethingelse00000000",)),
    )

    assert not cleared.viable
    scheduled = module.resolve_availability_wait(repo=repo, verdict=cleared, now_iso=_NOW)
    assert scheduled is not None
    assert scheduled.reevaluate_at == _EXPIRES_AT
