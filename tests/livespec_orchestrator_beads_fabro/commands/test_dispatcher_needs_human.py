"""Regression tests for the non-dispositive needs-human path.

Scenario 36 now forbids the Dispatcher from auto-resolving a
``blocked_reason: needs-human`` item. The old resolver module is intentionally
not imported here: the Green state deletes it, and these tests should fail on
assertions rather than collection.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    needs_attention,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_selection as loop_selection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput
from livespec_runtime.work_items.types import StoredBlockedReason, WorkItemStatus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESOLVER_SOURCE = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_needs_human.py"
)
_LOOP_SELECTION_SOURCE = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_loop_selection.py"
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        """{
  \"livespec-orchestrator-beads-fabro\": {
    \"connection\": {
      \"tenant\": \"livespec-impl-beads\",
      \"prefix\": \"bd\",
      \"server_user\": \"livespec-impl-beads\",
      \"database\": \"livespec-impl-beads\",
      \"bd_path\": \"bd\",
      \"fake\": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _item(
    *,
    status: WorkItemStatus = "blocked",
    blocked_reason: StoredBlockedReason | None = "needs-human",
) -> WorkItem:
    return WorkItem(
        id="bd-ib-needs-human",
        type="task",
        status=status,
        title="Needs a human",
        description="A decision only a human can make.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=blocked_reason,
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _blocked_outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run 01RUN parked at the in-loop human gate (needs-human)",
    )


def test_needs_human_resolver_module_is_removed() -> None:
    assert not _RESOLVER_SOURCE.exists()


def test_dispatcher_loop_selection_has_no_needs_human_resolver_call_site() -> None:
    source = _LOOP_SELECTION_SOURCE.read_text(encoding="utf-8")

    assert "_dispatcher_needs_human" not in source
    assert "resolve_or_bounce_needs_human" not in source


def test_dispatcher_pass_leaves_blocked_needs_human_item_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()

    def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return None

    monkeypatch.setattr(needs_attention, "_spec_next", _no_spec_next)
    if hasattr(loop_selection, "resolve_or_bounce_needs_human"):
        return

    post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=item,
        outcome=_blocked_outcome(item_id=item.id),
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    attention = needs_attention.build_attention(
        project_root=tmp_path, repo_name="repo", include_hygiene=False
    )

    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert any(entry.id == f"valve:resolve-blocked:{item.id}" for entry in attention)
    assert not any(record.get("stage") == "needs-human-resolved" for record in journal.records)
    assert not any(record.get("stage") == "blocked-bounce" for record in journal.records)


def test_needs_human_attention_is_json_queryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    append_work_item(path=_config(), item=_item())

    def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return None

    monkeypatch.setattr(needs_attention, "_spec_next", _no_spec_next)

    payload = json.loads(
        needs_attention.render_json(
            attention=needs_attention.build_attention(
                project_root=tmp_path, repo_name="repo", include_hygiene=False
            )
        )
    )

    assert [entry["id"] for entry in payload["attention"]] == [
        "valve:resolve-blocked:bd-ib-needs-human"
    ]


def test_dispatcher_blocked_outcome_writes_needs_human_ledger_and_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    item = _item(status="active", blocked_reason=None)
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    outcome = _blocked_outcome(item_id=item.id)

    _dispatcher_completion.escalate_needs_human_block(
        repo=tmp_path,
        item=item,
        outcome=outcome,
        journal=journal,
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    attention = _needs_attention_ids(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert "valve:resolve-blocked:bd-ib-needs-human" in attention
    assert {
        "stage": "needs-human-blocked",
        "work_item_id": item.id,
        "reason": "needs-human",
        "outcome_stage": "fabro-run",
        "outcome_status": "blocked",
    } in journal.records


def test_post_run_dispositions_persists_blocked_outcome_as_terminal_needs_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    item = _item(status="active", blocked_reason=None)
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()

    def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return None

    monkeypatch.setattr(needs_attention, "_spec_next", _no_spec_next)

    post_run_dispositions(
        args=argparse.Namespace(close_on_merge=True),
        repo=tmp_path,
        item=item,
        outcome=_blocked_outcome(item_id=item.id),
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    attention = needs_attention.build_attention(
        project_root=tmp_path, repo_name="repo", include_hygiene=False
    )

    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert any(entry.id == f"valve:resolve-blocked:{item.id}" for entry in attention)
    assert not any(record.get("stage") == "ledger-accept" for record in journal.records)


def test_human_valve_resolve_blocked_is_only_way_out(tmp_path: Path) -> None:
    _write_config(tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)

    result = run_human_valve_action(
        repo=tmp_path,
        action_id=f"resolve-blocked:{item.id}:ready",
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    assert stored.status == "ready"
    assert stored.blocked_reason is None


def _needs_attention_ids(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return None

    monkeypatch.setattr(needs_attention, "_spec_next", _no_spec_next)
    return [
        entry.id
        for entry in needs_attention.build_attention(
            project_root=tmp_path, repo_name="repo", include_hygiene=False
        )
    ]
