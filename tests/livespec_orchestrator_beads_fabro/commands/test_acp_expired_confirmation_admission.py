"""A factory-recorded success clears the expired hold it specifically confirms.

The candidate filter already understands confirmation evidence, but this test
drives the real admission preflight.  It prevents a regression where the
factory read produces successful attempts while the production preflight drops
them before candidate selection.

IT ALSO CARRIES THE OTHER RETIREMENT ROUTE INTO THE SAME SURFACE, and the two
cases are each other's control. A SUCCESS satisfies a post-expiry confirmation,
while a PEER'S OPERATOR CLEARANCE retires the expired observation outright --
and the clause requires that clearance to "make the affected wait eligible for
immediate reevaluation". Both arrive through the one factory read, so a build
that dropped either before candidate selection leaves the candidate skipped;
the two cases differ only in which evidence the factory row carries, which is
what makes each able to fail for its own reason rather than for the other's.

WHY THE CLEARANCE CASE CANNOT BE READ OFF THE SUCCESS CASE. A clearance is
applied as an observation-ID set at the host-wide union, where a peer's
factory-native record and this repository's own journal line both arrive; a
success is applied by the retirement predicate against each record's own scope.
So the two routes reach the expired half through different code, and the
measured defect hit only the clearance one: the union filtered its LIVE holds
by the merged retirement set and carried the EXPIRED half through unfiltered,
so the same ledger value reported an observation as retired while the candidate
filter reported an outstanding confirmation naming it.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_NOW = "2026-10-16T12:00:00Z"
_RUN_ID = "01M4TNCONFIRMED0000000000"
_CLEARANCE_RUN_ID = "01M4TNCLEARANCE0000000000"

# The expired observation BOTH cases are about, named once so the journal
# fixture and the clearance record cannot drift onto two ids -- a clearance
# naming an id the journal never recorded retires nothing, which is the one way
# the clearance case could pass while establishing nothing.
_OBSERVATION_ID = "expired-codex-observation"

_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},
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

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    start -> implement
    implement -> exit [label="green", condition="outcome=succeeded"]
"""


class _Reader:
    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self.rows if factory == "hp" else ()

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self.payloads.get(run_id) if factory == "hp" else None

    def __init__(self, *, rows: tuple[Any, ...], payloads: dict[str, object]) -> None:
        self.rows = rows
        self.payloads = payloads


def _module(name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _records() -> Any:
    """The clearance record module, so its label and render are never respelled.

    A hand-written label key or outcome line would make this fixture agree with
    a constant nobody rechecks: the read keys on the label before spending any
    per-run read, so a respelled key yields a row the evidence never inspects
    and the case would report a clearance that was never looked for.
    """
    return _module("_acp_clearance_records")


def _repo(tmp_path: Path) -> Path:
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_CONFIG, encoding="utf-8")
    return tmp_path


def _reader() -> _Reader:
    row = {
        "run_id": _RUN_ID,
        "status": {"kind": "succeeded"},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": "https://github.com/thewoolleyman/livespec-console-beads-fabro",
        "labels": {
            "livespec.repository": "livespec-console-beads-fabro",
            "livespec.acp.implement.availability": "codex",
            "livespec.acp.implement.candidate": "primary",
        },
        "start_time": "2026-10-16T11:56:00Z",
        "wall_time_ms": 60_000,
    }
    summaries = _module("_fabro_port_records").fabro_run_summaries_from_payload(payload=[row])
    payload = {
        _RUN_ID: [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "succeeded"},
                "checkpoint": {
                    "current_node": "exit",
                    "completed_nodes": ["implement", "exit"],
                    "node_outcomes": {"implement": {"status": "succeeded"}},
                },
            }
        ]
    }
    return _Reader(rows=summaries, payloads=payload)


def _expired_hold(journal: Path) -> None:
    journal.write_text(
        json.dumps(
            {
                "stage": "acp-availability-observed",
                "schema_version": 1,
                "observation_id": _OBSERVATION_ID,
                "scope": "availability-domain",
                "hold_key": "codex",
                "candidate_key": None,
                "cause": "quota",
                "occurred_at": "2026-10-16T11:40:00Z",
                "expires_at": "2026-10-16T11:55:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_factory_success_confirms_the_expired_observation_in_production_preflight(
    tmp_path: Path,
) -> None:
    """A current confirmation reaches selection instead of only direct unit tests."""
    repo = _repo(tmp_path)
    journal = repo / "dispatch.jsonl"
    _expired_hold(journal)

    verdict = _module("_dispatcher_acp_preflight").resolve_acp_preflight(
        repo=repo,
        journal_path=journal,
        now_iso=_NOW,
        factory_runs=_reader(),
    )

    node = verdict.node_preflight(node="implement")
    assert node.candidates[0].identity.candidate_key == "primary"
    assert node.skipped == ()


def _clearance_reader() -> _Reader:
    """A PEER repository's factory-native clearance of the expired observation.

    Labelled as a clearance record and carrying NO entitlement label, because a
    clearance spends no allowance -- so this row establishes the clearance route
    alone and cannot confirm the candidate by the success route instead.
    """
    row = {
        "run_id": _CLEARANCE_RUN_ID,
        "status": {"kind": "succeeded"},
        "goal": "Clear the codex availability domain hold\n",
        "repo_origin_url": "https://github.com/thewoolleyman/livespec-console-beads-fabro",
        "labels": {
            "livespec.repository": "livespec-console-beads-fabro",
            _records().CLEARANCE_LABEL_KEY: _records().CLEARANCE_LABEL_VALUE,
        },
        "start_time": "2026-10-16T11:56:00Z",
        "wall_time_ms": 1_000,
    }
    summaries = _module("_fabro_port_records").fabro_run_summaries_from_payload(payload=[row])
    recorded = _records().clearance_outcome_text(
        clearance=_records().AcpHoldClearance(
            scope="availability-domain",
            hold_key="codex",
            candidate_key=None,
            observation_ids=(_OBSERVATION_ID,),
            actor="operator:peer-maintainer",
            cleared_at="2026-10-16T11:57:00Z",
            reason="provider confirmed the window reset",
        )
    )
    payload = {
        _CLEARANCE_RUN_ID: [
            {
                "run_id": _CLEARANCE_RUN_ID,
                "status": {"kind": "succeeded"},
                "checkpoint": {
                    "current_node": "exit",
                    "completed_nodes": ["record", "exit"],
                    "node_outcomes": {"record": {"status": "succeeded", "output": recorded}},
                },
            }
        ]
    }
    return _Reader(rows=summaries, payloads=payload)


def test_a_peer_operator_clearance_retires_the_post_expiry_confirmation(
    tmp_path: Path,
) -> None:
    """A clearance recorded by a PEER makes the waiting candidate selectable.

    The clearance names the expired observation, so no outstanding availability
    confirmation survives it and the candidate is eligible for immediate
    reevaluation. Before the union filtered its expired half by the merged
    retirement set, this candidate stayed skipped on an observation the same
    ledger value reported as retired -- and because this item deliberately does
    not build the confirmation turn, that skip was indefinite rather than
    transient.
    """
    repo = _repo(tmp_path)
    journal = repo / "dispatch.jsonl"
    _expired_hold(journal)

    verdict = _module("_dispatcher_acp_preflight").resolve_acp_preflight(
        repo=repo,
        journal_path=journal,
        now_iso=_NOW,
        factory_runs=_clearance_reader(),
    )

    node = verdict.node_preflight(node="implement")
    assert node.skipped == ()
    assert node.candidates[0].identity.candidate_key == "primary"
