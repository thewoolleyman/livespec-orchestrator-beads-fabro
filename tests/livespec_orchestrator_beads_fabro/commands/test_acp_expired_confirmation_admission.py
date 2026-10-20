"""A factory-recorded success clears the expired hold it specifically confirms.

The candidate filter already understands confirmation evidence, but this test
drives the real admission preflight.  It prevents a regression where the
factory read produces successful attempts while the production preflight drops
them before candidate selection.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_NOW = "2026-10-16T12:00:00Z"
_RUN_ID = "01M4TNCONFIRMED0000000000"

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
                "observation_id": "expired-codex-observation",
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
