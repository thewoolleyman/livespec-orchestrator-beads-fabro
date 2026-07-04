"""Integration-tier acceptance for the Dispatcher admission + acceptance valves.

Binds SPECIFICATION/scenarios.md Scenarios 22-25 through the real
`dispatcher.main([...])` CLI + the real store/client seam against the
in-memory `FakeBeadsClient` (the hermetic CI backend), with `run_dispatch`
replaced by a recording stand-in so no fabro sandbox launches:

- Scenario 22 — the admission valve admits the highest-`rank` ready items up to
  the per-repo WIP cap, sets an assignee, and transitions them to `active`; the
  over-cap item waits at `ready`.
- Scenario 23 — a manual-admission item is held + surfaced, never admitted.
- Scenario 24 — `complete` merges on green into `acceptance` (not straight to
  `done`).
- Scenario 25 — `accept` honors the effective `acceptance_policy`
  (`ai-then-human` parks; `ai-only` confirms to `done`), and `reject` routes by
  corrective kind (`rework -> active`; `re-groom -> backlog`).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_DOER,
    reject_routing,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
    update_work_item_status,
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
    scratch = tmp_path_factory.mktemp("fabro-admission-acceptance")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._fetch_fleet_manifest_text",
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
        admission_policy="auto",
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path, wip_cap: int | None = None) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    block = '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
    if wip_cap is not None:
        block += f', "dispatcher": {{"wip_cap": {wip_cap}}}'
    block += "}}"
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


# ---------------------------------------------------------------------------
# Scenario 22 — admit the highest-rank ready items up to the per-repo WIP cap.
# ---------------------------------------------------------------------------


def test_loop_admits_highest_rank_up_to_wip_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=2)
    for rank in ("a0", "a1", "a2"):
        append_work_item(path=_config(), item=_item(id=f"bd-ib-{rank}", rank=rank))
    calls: list[str] = []
    monkeypatch.setattr(dispatcher, "run_dispatch", _green_recording(calls))

    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "3",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    assert exit_code == 0
    # Exactly the two highest-rank items are admitted (a0, a1); a2 waits.
    assert calls == ["bd-ib-a0", "bd-ib-a1"]
    stored = _stored()
    assert (stored["bd-ib-a0"].status, stored["bd-ib-a0"].assignee) == ("active", DEFAULT_DOER)
    assert (stored["bd-ib-a1"].status, stored["bd-ib-a1"].assignee) == ("active", DEFAULT_DOER)
    # a2 is capacity-deferred: not admitted, still ready, no assignee.
    assert (stored["bd-ib-a2"].status, stored["bd-ib-a2"].assignee) == ("ready", None)


# ---------------------------------------------------------------------------
# Scenario 23 — a manual-admission item is held until approved.
# ---------------------------------------------------------------------------


def test_loop_holds_manual_admission_item(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, wip_cap=5)
    item = _item(id="bd-ib-manual", status="pending-approval", admission_policy="manual")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(dispatcher, "run_dispatch", _green_recording(calls))

    exit_code = main(
        [
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

    # The held item rides in the outcomes as a non-green terminal.
    assert exit_code == 1
    assert calls == []
    # Not admitted: it stays pending-approval for the maintainer to approve.
    assert _stored()[item.id].status == "pending-approval"
    # Surfaced for the maintainer (stderr) and journaled.
    err = capsys.readouterr().err
    assert "approval held" in err
    assert item.id in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line).get("stage") for line in journal_text.splitlines()]
    assert "outcome" in stages


# ---------------------------------------------------------------------------
# Scenario 24 — complete merges on green into the acceptance state.
# ---------------------------------------------------------------------------


def test_complete_merges_on_green_into_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    # Default acceptance_policy ai-then-human -> parks in acceptance after the
    # AI pass (does NOT go straight to done).
    item = _item(id="bd-ib-acc")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _green_recording([]))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 0
    stored = _stored()[item.id]
    # The green run merged (run_dispatch) and the item completed into the
    # observable acceptance state — NOT straight to done.
    assert stored.status == "acceptance"
    assert stored.resolution is None
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line).get("stage") for line in journal_text.splitlines()]
    assert "ledger-complete" in stages
    assert "acceptance-ai-pass" in stages
    assert "acceptance-parked" in stages
    assert "ledger-accept" not in stages


# ---------------------------------------------------------------------------
# Scenario 25 — accept per acceptance_policy; reject routes by corrective kind.
# ---------------------------------------------------------------------------


def test_accept_ai_then_human_parks_until_human(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="bd-ib-park", acceptance_policy="ai-then-human")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _green_recording([]))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 0
    # Parked in acceptance on the ledger; it reaches done only after a human
    # confirms (the L2 console path), never autonomously.
    assert _stored()[item.id].status == "acceptance"


def test_accept_ai_only_confirms_to_done(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="bd-ib-aionly", acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(dispatcher, "run_dispatch", _green_recording([]))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 0
    stored = _stored()[item.id]
    # The AI pass confirmed and accepted autonomously -> done + completed.
    assert (stored.status, stored.resolution) == ("done", "completed")


def test_reject_rework_routes_to_active() -> None:
    item = _item(id="bd-ib-rew", status="acceptance")
    append_work_item(path=_config(), item=item)
    # The Dispatcher is the sole enforcer: reject(rework) is a fix-forward
    # patch on the live change -> back to active.
    update_work_item_status(path=_config(), item_id=item.id, status=reject_routing(kind="rework"))
    assert _stored()[item.id].status == "active"


def test_reject_regroom_routes_to_backlog() -> None:
    item = _item(id="bd-ib-rgr", status="acceptance")
    append_work_item(path=_config(), item=item)
    # reject(re-groom) reverts the merged change and re-decomposes -> backlog.
    update_work_item_status(path=_config(), item_id=item.id, status=reject_routing(kind="re-groom"))
    assert _stored()[item.id].status == "backlog"
