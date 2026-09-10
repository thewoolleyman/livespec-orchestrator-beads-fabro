"""Tests pinning the loop selection surface for queue drains and item dispatches.

bd-ib-mqunvm: loop drains the ranked queue by default, --item targets one
work item, --dry-run plans without dispatching, and the retired --mode flag is
rejected by argparse.
"""

import json
import stat
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
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

# A minimal workflow graph for the payload materializer to render: one node
# timeout plus the run-level stall watchdog, which is the shape the literal-
# duration rewrite requires (commands/_dispatcher_graph_render.py).
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def fabro_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    scratch = tmp_path_factory.mktemp("fabro-item-mode")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
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
        status="ready",
        title="A ready task",
        description="Do the thing.",
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
        # Admission-eligible by default so a dispatched item flows through the
        # admission valve (ready -> active); the WIP-cap / hold cases override.
        admission_policy="auto",
        acceptance_policy="ai-only",
        # A dispatchable fixture carries gradeable criteria: the entry-to-`ready`
        # and pre-dispatch walls (the effective-acceptance-criteria clause of contracts.md)
        # refuse an AI-dispositive item whose effective criteria parse to zero
        # gradeable assertions.
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _read_items() -> dict[str, WorkItem]:
    return {item.id: item for item in read_work_items(path=_config())}


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    # The dispatcher resolves the tenant connection via
    # resolve_store_config(cwd=repo), which REQUIRES an explicit
    # connection.prefix (decoupled from the tenant DB name); a real governed
    # repo always carries one, so the hermetic repo mirrors that.
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


@dataclass(kw_only=True)
class _RecordingRunDispatch:
    """run_dispatch stand-in: records dispatched work_item_ids and returns green."""

    calls: list[str] = field(default_factory=list)
    factories: list[str] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        _ = plan.workflow_toml.read_text(encoding="utf-8")
        _ = stat.S_IMODE(plan.workflow_toml.stat().st_mode)
        self.calls.append(plan.work_item_id)
        self.factories.append(plan.fabro_factory_name)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="abc123",
            detail="merged",
        )


def test_loop_help_shows_dry_run_and_not_retired_mode(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ = main(argv=["loop", "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--dry-run" in help_text
    assert "--mode" not in help_text


def test_loop_rejects_retired_mode_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ = main(
            argv=[
                "loop",
                "--repo",
                "/tmp/repo",
                "--budget",
                "1",
                "--mode",
                "autonomous",
            ]
        )

    assert exc_info.value.code == 2
    assert "--mode" in capsys.readouterr().err


def test_loop_without_item_drains_ranked_queue_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", rank="a1")
    second = _item(id="b-2", rank="a2")
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "2",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    assert exit_code == 0
    assert recording.calls == ["a-1", "b-2"]


def test_loop_without_candidates_emits_nothing_dispatched(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    assert "(nothing dispatched)" in capsys.readouterr().out
    assert recording.calls == []


def test_loop_with_item_dispatches_requested_not_top_ranked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop --item <id> dispatches exactly the requested item.

    When two items are ready, a-1 (rank="a1") ranks first and b-2
    (rank="a2") ranks second. Passing --item b-2 must dispatch b-2, not
    drain the top-ranked a-1.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    high_priority = _item(id="a-1", rank="a1")
    requested = _item(id="b-2", rank="a2")
    append_work_item(path=_config(), item=high_priority)
    append_work_item(path=_config(), item=requested)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--item",
            "b-2",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert recording.calls == ["b-2"]


def test_dispatch_records_factory_and_retry_reuses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="factory-pinned")
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    first_exit = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--item",
            "factory-pinned",
            "--factory",
            "remote",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    update_work_item_status(path=_config(), item_id="factory-pinned", status="ready")
    second_exit = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--item",
            "factory-pinned",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    comments = read_work_item_comments(path=_config(), work_item_id="factory-pinned")
    assert first_exit == 0
    assert second_exit == 0
    assert recording.factories == ["remote", "remote"]
    assert [comment.text for comment in comments].count("livespec-dispatch-factory: remote") == 1


def test_loop_dry_run_plans_selection_without_dispatch_or_ledger_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", rank="a1")
    second = _item(id="b-2", rank="a2")
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--dry-run",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    assert recording.calls == []
    stored = _read_items()
    assert stored["a-1"].status == "ready"
    assert stored["b-2"].status == "ready"
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    pick = next(record for record in records if record["stage"] == "loop-pick")
    assert pick["dry_run"] is True
    assert pick["budget"] == 1
    assert pick["picked"] == ["a-1"]


def _loop_pick_record(*, repo: Path) -> dict[str, object]:
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    record = next(record for record in records if record["stage"] == "loop-pick")
    assert isinstance(record, dict)
    return record


def test_loop_dry_run_reports_picked_ids_in_its_json_outcome_list(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run --json reports the picks, and they equal the loop-pick record.

    bd-ib-omvia6: the dry-run branch emitted an unconditional empty outcome
    list, so the "what would this drain do?" surface answered `[]` while the
    selection sat only in the gitignored journal. Three ready items against a
    budget of 2 pin the budget honoring at the same time.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(id="a-1", rank="a1"))
    append_work_item(path=_config(), item=_item(id="b-2", rank="a2"))
    append_work_item(path=_config(), item=_item(id="c-3", rank="a3"))
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "2",
            "--dry-run",
            "--json",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    reported = [entry["work_item_id"] for entry in payload]
    assert reported == ["a-1", "b-2"]
    pick = _loop_pick_record(repo=repo)
    assert pick["dry_run"] is True
    assert reported == pick["picked"]
    assert recording.calls == []
    stored = _read_items()
    assert [stored[item_id].status for item_id in ("a-1", "b-2", "c-3")] == ["ready"] * 3


def test_loop_dry_run_prints_the_picked_id_for_an_explicit_item_filter(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The human stdout line names the picked id, honoring --item.

    b-2 ranks second, so a filtered dry-run reporting b-2 alone proves the
    reported picks follow the item filter rather than the ranked head.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(id="a-1", rank="a1"))
    append_work_item(path=_config(), item=_item(id="b-2", rank="a2"))
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "2",
            "--dry-run",
            "--item",
            "b-2",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "b-2" in stdout
    assert "a-1" not in stdout
    assert _loop_pick_record(repo=repo)["picked"] == ["b-2"]
    assert recording.calls == []


def test_loop_dry_run_reports_an_empty_outcome_list_without_candidates(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no ready work the dry-run outcome list is empty, not fabricated."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "2",
            "--dry-run",
            "--json",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == []
    assert _loop_pick_record(repo=repo)["picked"] == []
    assert recording.calls == []


def test_loop_with_item_not_ready_exits_precondition_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop --item <not-ready-id> exits 3 with a clear error.

    A closed item is not in the ready set; an item-specific dispatch must
    fail clearly rather than silently dispatching nothing (exit 0).
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    closed_item = _item(id="closed-item", status="done", resolution="completed")
    append_work_item(path=_config(), item=closed_item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    exit_code = main(
        argv=[
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


def test_loop_with_item_at_wip_cap_emits_capacity_deferred_result(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    active = _item(id="active-claim", status="active", assignee="fabro")
    requested = _item(id="requested-ready", status="ready", rank="a1")
    append_work_item(path=_config(), item=active)
    append_work_item(path=_config(), item=requested)
    _ = write_dispatch_lock(repo=repo, work_item_id=active.id, dispatch_id="live-dispatch")
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--item",
            requested.id,
            "--json",
            "--workflow",
            str(workflow),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == [
        {
            "detail": (
                "capacity deferred: active_count=1 wip_cap=1 free_slots=0 "
                "live_lock_active_ids=active-claim "
                "single_item_override=dispatcher.py dispatch --item requested-ready "
                "single_item_override_enforces_cap=false "
                "single_item_override_cost=deliberately_exceeds_wip_cap_bound_for_same_repo_"
                "merge_rebase_contention_during_unattended_draining"
            ),
            "fabro_run_id": None,
            "merge_sha": None,
            "pr_number": None,
            "stage": "capacity-deferred",
            "status": "capacity-deferred",
            "work_item_id": requested.id,
        }
    ]
    assert recording.calls == []
    assert _read_items()[requested.id].status == "ready"
