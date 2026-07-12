"""Integration-tier acceptance for full autonomous mode's two-valve collapse (S3).

Binds SPECIFICATION/scenarios.md Scenarios 33, 34, and 36 through the real
`dispatcher.main(argv=[...])` CLI + the real store/client seam against the
in-memory `FakeBeadsClient`, with `run_dispatch` replaced by a recording
stand-in so no fabro sandbox launches:

- Scenario 33 — an armed run auto-approves a routine `manual` `pending-approval`
  item into `ready` (then admits it mechanically) and journals the auto-approval
  as an autonomous auto-resolution audit record (`gate` `approve`).
- Scenario 34 — an armed run accepts an `ai-then-human` item to `done` on the
  passing AI pass (no human leg) and journals the auto-acceptance (`gate`
  `acceptance`); at least one AI pass ran.
- Scenario 36 — the two escape hatches hold even under an armed run: a
  design-human-gated spec-change-tier slice stays HELD at `pending-approval`
  (admission backstop), and a `human-only` item still PARKS in `acceptance`.
- Not-armed invariant — `--mode autonomous` WITHOUT the persistent permission
  is not armed, so a routine `manual` item is held exactly as before (no
  collapse, no audit record).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-autonomous-collapse")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-s1",
        type="task",
        status="pending-approval",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="manual",
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path, autonomous_mode: bool) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher_block = (
        '"dispatcher": {' + f'"autonomous_mode": {"true" if autonomous_mode else "false"}' + "}"
    )
    block = (
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        + dispatcher_block
        + "}}"
    )
    _ = (repo / ".livespec.jsonc").write_text(block, encoding="utf-8")
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return repo, workflow


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _green_recording(calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in that records each launch and returns green."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=11,
            merge_sha="feed01",
            detail="merged",
        )

    return _run_dispatch


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _autonomous_decisions(*, repo: Path, gate: str) -> list[dict[str, object]]:
    return [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == "autonomous-decision" and record.get("gate") == gate
    ]


# ---------------------------------------------------------------------------
# Scenario 33 — armed run auto-approves a routine manual pending item.
# ---------------------------------------------------------------------------


def test_armed_auto_approves_routine_manual_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, autonomous_mode=True)
    item = _item(id="bd-ib-routine", status="pending-approval", admission_policy="manual")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    assert exit_code == 0
    # Auto-approved into ready then admitted mechanically to active + dispatched.
    assert calls == [item.id]
    assert _stored()[item.id].status == "active"
    # The auto-approval is journaled as an autonomous auto-resolution audit record.
    decisions = _autonomous_decisions(repo=repo, gate="approve")
    assert [d.get("work_item_id") for d in decisions] == [item.id]
    assert decisions[0].get("disposition") == "auto-resolved"


# ---------------------------------------------------------------------------
# Scenario 34 — armed run accepts an ai-then-human item to done on the AI pass.
# ---------------------------------------------------------------------------


def test_armed_auto_accepts_ai_then_human_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, autonomous_mode=True)
    item = _item(
        id="bd-ib-acc", status="ready", admission_policy="auto", acceptance_policy="ai-then-human"
    )
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording([]))

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    stored = _stored()[item.id]
    # Accepted to done on the AI pass alone — no human accept leg.
    assert (stored.status, stored.resolution) == ("done", "completed")
    stages = [record.get("stage") for record in _journal_records(repo=repo)]
    # The AI pass STILL ran first (no release with zero verification), and the
    # item did NOT park.
    assert "acceptance-ai-pass" in stages
    assert "acceptance-parked" not in stages
    decisions = _autonomous_decisions(repo=repo, gate="acceptance")
    assert [d.get("work_item_id") for d in decisions] == [item.id]
    assert decisions[0].get("disposition") == "auto-resolved"


# ---------------------------------------------------------------------------
# Scenario 36 — the human-only acceptance still parks even under an armed run.
# ---------------------------------------------------------------------------


def test_armed_human_only_acceptance_still_parks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, autonomous_mode=True)
    item = _item(
        id="bd-ib-human", status="ready", admission_policy="auto", acceptance_policy="human-only"
    )
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording([]))

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    # A deliberate human gate: still parks in acceptance, never auto-accepted.
    assert _stored()[item.id].status == "acceptance"
    stages = [record.get("stage") for record in _journal_records(repo=repo)]
    assert "acceptance-parked" in stages
    assert "ledger-accept" not in stages
    # No acceptance collapse audit record — the mode did NOT auto-resolve it.
    assert _autonomous_decisions(repo=repo, gate="acceptance") == []


# ---------------------------------------------------------------------------
# Scenario 36 — a spec-change-tier slice stays HELD (the admission backstop).
# ---------------------------------------------------------------------------


def test_armed_spec_change_tier_item_stays_held(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, autonomous_mode=True)
    # A manual pending item carrying a spec-commitment linkage reads as
    # design-human-gated spec-change-tier — the conservative backstop holds it.
    item = _item(
        id="bd-ib-spec",
        status="pending-approval",
        admission_policy="manual",
        spec_commitment_hint="pc4-followup-3",
    )
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )

    # Held, never dispatched, and not collapsed: it stays pending-approval.
    assert exit_code == 1
    assert calls == []
    assert _stored()[item.id].status == "pending-approval"
    assert "approval held" in capsys.readouterr().err
    assert _autonomous_decisions(repo=repo, gate="approve") == []


# ---------------------------------------------------------------------------
# Not-armed invariant — the flag without the permission collapses nothing.
# ---------------------------------------------------------------------------


def test_flag_without_permission_holds_routine_manual_item(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # autonomous_mode permission OFF: `--mode autonomous` alone is the ordinary
    # full-queue drain, so a routine manual item is held exactly as before.
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, autonomous_mode=False)
    item = _item(id="bd-ib-routine", status="pending-approval", admission_policy="manual")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(calls))

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 1
    assert calls == []
    assert _stored()[item.id].status == "pending-approval"
    assert "approval held" in capsys.readouterr().err
    assert _autonomous_decisions(repo=repo, gate="approve") == []
