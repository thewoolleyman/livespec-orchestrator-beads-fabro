"""Tests pinning the mode/item interaction for item-specific dispatches.

bd-ib-2qv7mk: autonomous mode with --item must dispatch exactly the
requested item, not drain an unrelated top-ranked item; a requested item
that is not in the ready set must fail clearly with exit 3 regardless of
mode.
"""

import stat
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// fleet-manifest.jsonc — canned test copy\n"
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
def fabro_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    scratch = tmp_path_factory.mktemp("fabro-item-mode")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("GH_TOKEN", "test-github-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="open",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return repo, workflow


@dataclass(kw_only=True)
class _RecordingRunDispatch:
    """run_dispatch stand-in: records dispatched work_item_ids and returns green."""

    calls: list[str] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        _ = plan.workflow_toml.read_text(encoding="utf-8")
        _ = stat.S_IMODE(plan.workflow_toml.stat().st_mode)
        self.calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="abc123",
            detail="merged",
        )


def test_loop_autonomous_with_item_dispatches_requested_not_top_ranked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop --mode autonomous --item <id> dispatches exactly the requested item.

    When two items are ready, a-1 (priority=1) ranks first and b-2
    (priority=2) ranks second.  Passing --item b-2 must dispatch b-2, not
    drain the top-ranked a-1 — the bug this test pins.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    high_priority = _item(id="a-1", priority=1)
    requested = _item(id="b-2", priority=2)
    append_work_item(path=_config(), item=high_priority)
    append_work_item(path=_config(), item=requested)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--item",
            "b-2",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert recording.calls == ["b-2"]


def test_loop_autonomous_with_item_not_ready_exits_precondition_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop --mode autonomous --item <not-ready-id> exits 3 with a clear error.

    A closed item is not in the ready set; an item-specific dispatch must
    fail clearly rather than silently dispatching nothing (exit 0).
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    closed_item = _item(id="closed-item", status="closed", resolution="completed")
    append_work_item(path=_config(), item=closed_item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--item",
            "closed-item",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 3
    assert "closed-item" in capsys.readouterr().err
    assert recording.calls == []


def test_loop_shadow_with_item_not_ready_exits_precondition_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop --mode shadow --item <not-ready-id> exits 3 with a clear error.

    Shadow mode with an explicitly requested item that is not ready must
    also fail clearly, consistent with the dispatch subcommand's contract.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    closed_item = _item(id="closed-item", status="closed", resolution="completed")
    append_work_item(path=_config(), item=closed_item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)
    exit_code = main(
        [
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--item",
            "closed-item",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 3
    assert "closed-item" in capsys.readouterr().err
    assert recording.calls == []
