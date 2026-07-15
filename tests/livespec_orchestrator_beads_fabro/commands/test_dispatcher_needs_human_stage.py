"""Acceptance coverage for the needs-human resolve-or-escalate wiring stage (S4).

Drives `_dispatcher_needs_human.resolve_or_bounce_needs_human` and its helpers through the
FAKE `RecordingNeedsHumanResolver` (NO real model call) to prove
`SPECIFICATION/scenarios.md` Scenarios 35 and 36:

- Scenario 35 — an armed, confidently-resolvable `needs-human` block is
  auto-resolved and routed back onto its normal path (`ready`) with an
  `auto-resolved` per-decision audit record.
- Scenario 36 — a low-confidence block AND a design-human-gated block (even at
  high confidence) are left escalated (bounced to `backlog` + surfaced) with
  `escalated` audit records.

Plus the not-armed / non-blocked pass-through (exactly the pre-existing
`_bounce_blocked`) and the fail-soft ledger-write branch.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_needs_human as needs_human
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_audit import (
    AUTONOMOUS_DECISION_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human import (
    NeedsHumanResolution,
    RecordingNeedsHumanResolver,
    resolve_or_bounce_needs_human,
    route_needs_human_resolved,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main as dispatcher_main
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.list_work_items import main as list_work_items_main
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = _repo(tmp_path=tmp_path)
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(
        '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n',
        encoding="utf-8",
    )
    return repo, workflow


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-nh1",
        type="task",
        status="active",
        title="A parked task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _blocked(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run 01RUN parked at the in-loop human gate (needs-human)",
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _armed() -> argparse.Namespace:
    return argparse.Namespace(autonomous_armed=True)


def _audit_records(journal: _RecordingJournal) -> list[dict[str, object]]:
    return [r for r in journal.records if r.get("stage") == AUTONOMOUS_DECISION_STAGE]


# ---------------------------------------------------------------------------
# Dispatcher-level needs-human ledger escalation
# ---------------------------------------------------------------------------


def test_block_needs_human_is_terminal_until_drive_human_valve(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="bd-ib-blocked", status="active")
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()

    assert hasattr(needs_human, "block_needs_human")
    needs_human.block_needs_human(
        repo=repo, item=item, reason="operator judgment needed", journal=journal
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    assert any(
        record
        == {
            "stage": "needs-human-blocked",
            "work_item_id": item.id,
            "reason": "operator judgment needed",
        }
        for record in journal.records
    )

    list_work_items_main(argv=["--project-root", str(repo), "--json"])
    listed = {entry["id"]: entry for entry in json.loads(capsys.readouterr().out)}
    assert listed[item.id]["status"] == "blocked"
    assert listed[item.id]["blocked_reason"] == "needs-human"

    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {'
        '"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"auto_approve_ready": true}}}',
        encoding="utf-8",
    )
    exit_code = dispatcher_main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
            "--skip-ledger-check",
            "--json",
        ]
    )

    assert exit_code == 0
    assert _stored()[item.id].status == "blocked"

    result = run_action(repo=repo, action_id=f"unblock:{item.id}:ready")

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    unblocked = _stored()[item.id]
    assert (unblocked.status, unblocked.blocked_reason) == ("ready", None)


# ---------------------------------------------------------------------------
# Scenario 35 — resolve + route back
# ---------------------------------------------------------------------------


def test_armed_resolvable_block_routes_back_to_ready_and_audits(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    resolver = RecordingNeedsHumanResolver(
        verdict=NeedsHumanResolution(
            resolvable=True, design_gated=False, decision="cleared the ambiguity"
        )
    )

    resolve_or_bounce_needs_human(
        args=_armed(),
        repo=repo,
        item=item,
        outcome=_blocked(item_id=item.id),
        journal=journal,
        resolver=resolver,
    )

    # Routed back onto its normal path, NOT bounced to backlog.
    assert _stored()[item.id].status == "ready"
    # The resolver was consulted (no real model call — the fake recorded it).
    assert resolver.calls == [(item.id, _blocked(item_id=item.id).detail)]
    audits = _audit_records(journal)
    assert len(audits) == 1
    assert audits[0]["gate"] == "needs-human"
    assert audits[0]["disposition"] == "auto-resolved"
    assert audits[0]["decision"] == "cleared the ambiguity"
    assert any(r.get("stage") == "needs-human-resolved" for r in journal.records)
    # It is NOT escalated: no blocked-bounce.
    assert not any(r.get("stage") == "blocked-bounce" for r in journal.records)


# ---------------------------------------------------------------------------
# Scenario 36 — escalate the low-confidence and the design-gated
# ---------------------------------------------------------------------------


def test_armed_low_confidence_block_escalates_to_backlog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    resolver = RecordingNeedsHumanResolver(
        verdict=NeedsHumanResolution(
            resolvable=False, design_gated=False, decision="needs a human judgment call"
        )
    )

    resolve_or_bounce_needs_human(
        args=_armed(),
        repo=repo,
        item=item,
        outcome=_blocked(item_id=item.id),
        journal=journal,
        resolver=resolver,
    )

    # Left escalated: bounced to backlog and surfaced.
    assert _stored()[item.id].status == "backlog"
    assert any(r.get("stage") == "blocked-bounce" for r in journal.records)
    assert "bounced to backlog" in capsys.readouterr().err
    audits = _audit_records(journal)
    assert len(audits) == 1
    assert audits[0]["disposition"] == "escalated"
    assert audits[0]["gate"] == "needs-human"
    assert not any(r.get("stage") == "needs-human-resolved" for r in journal.records)


def test_armed_design_gated_block_escalates_by_design(tmp_path: Path) -> None:
    # Scenario 36 leg 2: a drift-acceptance decision the LLM COULD resolve with
    # high confidence is still reserved to a human.
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    resolver = RecordingNeedsHumanResolver(
        verdict=NeedsHumanResolution(
            resolvable=True, design_gated=True, decision="drift acceptance is human-owned"
        )
    )

    resolve_or_bounce_needs_human(
        args=_armed(),
        repo=repo,
        item=item,
        outcome=_blocked(item_id=item.id),
        journal=journal,
        resolver=resolver,
    )

    assert _stored()[item.id].status == "backlog"
    audits = _audit_records(journal)
    assert len(audits) == 1
    assert audits[0]["disposition"] == "escalated"
    assert not any(r.get("stage") == "needs-human-resolved" for r in journal.records)


def test_armed_human_only_item_escalates_even_when_resolvable(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(acceptance_policy="human-only")
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    resolver = RecordingNeedsHumanResolver(
        verdict=NeedsHumanResolution(resolvable=True, design_gated=False, decision="could resolve")
    )

    resolve_or_bounce_needs_human(
        args=_armed(),
        repo=repo,
        item=item,
        outcome=_blocked(item_id=item.id),
        journal=journal,
        resolver=resolver,
    )

    assert _stored()[item.id].status == "backlog"
    assert _audit_records(journal)[0]["disposition"] == "escalated"


# ---------------------------------------------------------------------------
# Not-armed / non-blocked pass-through (exactly the pre-existing bounce)
# ---------------------------------------------------------------------------


def test_not_armed_blocked_bounces_unchanged_and_builds_the_default_resolver(
    tmp_path: Path,
) -> None:
    # resolver=None exercises the default `ClaudeNeedsHumanResolver` construction
    # (never CALLED here — the run is not armed, so it bounces exactly as before).
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()

    resolve_or_bounce_needs_human(
        args=argparse.Namespace(),
        repo=repo,
        item=item,
        outcome=_blocked(item_id=item.id),
        journal=journal,
    )

    assert _stored()[item.id].status == "backlog"
    assert any(r.get("stage") == "blocked-bounce" for r in journal.records)
    # No autonomous decision is journaled when the run is not armed.
    assert _audit_records(journal) == []


def test_armed_non_blocked_outcome_is_a_noop(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _RecordingJournal()
    resolver = RecordingNeedsHumanResolver(
        verdict=NeedsHumanResolution(resolvable=True, design_gated=False, decision="n/a")
    )
    green = DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha="feed01",
        detail="merged",
    )

    resolve_or_bounce_needs_human(
        args=_armed(),
        repo=repo,
        item=item,
        outcome=green,
        journal=journal,
        resolver=resolver,
    )

    # A non-blocked terminal never reaches the resolver and never audits.
    assert resolver.calls == []
    assert _audit_records(journal) == []
    assert not any(r.get("stage") == "blocked-bounce" for r in journal.records)


# ---------------------------------------------------------------------------
# Fail-soft ledger write on the resolve route-back
# ---------------------------------------------------------------------------


def test_route_back_failsoft_journals_error_when_ledger_write_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item()
    journal = _RecordingJournal()

    def _raise(**_kwargs: object) -> None:
        raise WorkItemNotFoundError(item_id=item.id)

    monkeypatch.setattr(needs_human, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(needs_human, "update_work_item_status", _raise)

    # Must NOT raise — the resolve is already decided.
    route_needs_human_resolved(
        repo=tmp_path,
        item=item,
        journal=journal,
        resolution=NeedsHumanResolution(resolvable=True, design_gated=False, decision="x"),
    )

    errors = [r for r in journal.records if r.get("stage") == "needs-human-resolve-error"]
    assert len(errors) == 1
    assert errors[0]["work_item_id"] == item.id
    assert errors[0]["reason"] == "WorkItemNotFoundError"
    assert not any(r.get("stage") == "needs-human-resolved" for r in journal.records)
