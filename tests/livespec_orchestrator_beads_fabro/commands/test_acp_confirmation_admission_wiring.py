"""Admission RUNS the confirmation turn an expired hold leaves owing, before refusing.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry" (Scenario 60, "An
observed provider exhaustion refuses admission, and expires", and the scenario
"An expired hold is re-confirmed by a completed turn before a real dispatch
uses the candidate") to the production admission path.

THE DEFECT THIS BINDS (`bd-ib-i4nert`): the filter's confirmation seam, the
probe's shape and the turn that performs it were all built, and NOTHING in
production supplied the seam. An expired provider-wide hold therefore left every
candidate it covered owing a confirmation that no code path ever ran, so a
tenant with no successful dispatch refused every admission, indefinitely, with
an empty `confirmation_turn_endings`. The cause was neither a configuration gate
nor `loop --item` failing to reach the probe: no entry point reached it.

HERMETIC: the fabro engine is a recording fake and the factory run listing is a
fake reader; nothing launches an adapter or reaches a provider.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBE00000000000000000"

_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},
      "acp_nodes": {
        "implement": {
          "display_name": "Primary",
          "candidate_key": "primary",
          "availability_key": "anthropic",
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
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    fix [backend="acp", acp.command="b", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
    gate -> fix [label="red"]
    fix -> gate
"""


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner whose confirmation turn ends as the case says."""

    node_state: str = "succeeded"
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv:
            record: dict[str, Any] = {
                "run_id": _RUN_ID,
                "status": {"kind": "succeeded" if self.node_state == "succeeded" else "failed"},
                "total_usd_micros": 7300,
                "stages": {"confirm@1": {"state": self.node_state}},
            }
            return _Command(exit_code=0, stdout=json.dumps([record]))
        if "events" in argv:
            events = [{"event_id": "e1", "type": "agent.acp.started", "node": "confirm"}]
            return _Command(exit_code=0, stdout=json.dumps(events))
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")

    def launches(self) -> list[list[str]]:
        return [argv for argv in self.calls if "run" in argv and "--version" not in argv]


class _EmptyFactory:
    """A factory run listing that is readable and carries no run at all."""

    def __init__(self, *, repo: Path) -> None:
        self.repo = repo

    def list_runs(self, *, factory: str) -> tuple[()]:
        _ = factory
        return ()


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item(*, item_id: str) -> Any:
    types = importlib.import_module("livespec_orchestrator_beads_fabro.types")
    return types.WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="Task",
        description="Do it.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy=None,
        acceptance_policy=None,
    )


def _expired_domain_hold_row() -> dict[str, object]:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    return {
        "stage": records.HOLD_STAGE,
        "schema_version": records.HOLD_SCHEMA_VERSION,
        "observation_id": "acp-expired0001",
        "scope": classifier.DOMAIN_SCOPE,
        "hold_key": "anthropic",
        "candidate_key": None,
        "cause": "quota",
        "evidence_kind": "acp-failover-event",
        "evidence_id": "petri:01M5S6FRWK93019DZVV3S5GS60:proof_capture",
        "occurred_at": "2026-10-25T10:21:34Z",
        "expires_at": "2026-10-25T10:36:34Z",
        "work_item_id": "bd-gj-oqko6n",
        "node": "proof_capture",
    }


def _admit(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: _Engine) -> Any:
    """Admit one ready item against a journal holding one expired provider-wide hold."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(_CONFIG, encoding="utf-8")
    journal_path = tmp_path / "journal.jsonl"
    _ = journal_path.write_text(json.dumps(_expired_domain_hold_row()) + "\n", encoding="utf-8")

    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    probe_run = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(admission_module, "session_headroom_policy", lambda **_: None)
    monkeypatch.setattr(admission_module, "FactoryRunReader", _EmptyFactory)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(probe_run, "ShellCommandRunner", lambda: engine)
    journal = io_module.JournalFile(path=journal_path)

    return admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(item_id="bd-ib-low-traffic")],
        journal=journal,
        enforce_cap=False,
    )


def test_admission_runs_the_owed_confirmation_turn_before_refusing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first Then: the probe runs, and admission re-evaluates with its outcome."""
    engine = _Engine()

    admission = _admit(tmp_path=tmp_path, monkeypatch=monkeypatch, engine=engine)

    # One turn per candidate the expired hold covers: the primary and its fallback
    # carry distinct candidate keys, and a turn through one confirms nothing about
    # its sibling.
    assert len(engine.launches()) == 2
    assert [item.id for item in admission.admitted] == ["bd-ib-low-traffic"]
    assert admission.refused == []
