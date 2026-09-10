"""Integration-tier acceptance for the human rework reject's selectability.

Binds `SPECIFICATION/scenarios.md` "Scenario 67 — The human rework reject parks
the same selectable state" through the real `drive.run_action` valve, the real
`dispatcher.main(argv=["dispatch", ...])` CLI, and the real store/client seam
against the in-memory `FakeBeadsClient`, with `run_dispatch` replaced by a
recording stand-in so no fabro sandbox launches.

The two rework entries — an AI-fail disposition and a human `reject:rework` —
are covered separately elsewhere, and each is correct in isolation. What no
existing case can observe is whether they PARK THE SAME STATE, because that is a
property of the two paths meeting: the state one writes must be the state the
other's consumer selects. So this case does not assert the label; it hands the
item the human valve produced straight to the dispatch surface and requires it
to be taken.

The unmarked control is what makes that meaningful. `dispatch --item` refusing a
bare `active` row is the rule the marked item is an exception to, so without it
"the dispatch was accepted" would be equally consistent with the surface
accepting any active row at all.
"""

from __future__ import annotations

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
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXIT_PRECONDITION_ERROR = 3
_REWORK_ADMIT_STAGE = "ledger-rework-admit"

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
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-rework-reject")
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
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-rejected",
        type="task",
        status="acceptance",
        title="A slice parked in acceptance",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria="The reworked slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 3, "acceptance_mode": "ai-only"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _stored(*, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id]


def _recording(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
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


def test_the_human_reject_parks_a_state_dispatch_takes_immediately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls))

    rejected = run_action(repo=repo, action_id=f"reject:{item.id}:rework")

    assert rejected["status"] == "green"
    parked = _stored(item_id=item.id)
    assert (parked.status, parked.rework_pending) == ("active", True)

    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    # Accepted, and admitted through the rework leg rather than as a fresh
    # `ready -> active` admission: the valve the operator was offered is not a
    # dead end.
    assert (exit_code, calls) == (0, [item.id])
    journal = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert _REWORK_ADMIT_STAGE in journal


def test_an_active_item_without_the_marker_is_refused_as_a_precondition_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="bd-ib-bare", status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording(calls=calls))

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert (exit_code, calls) == (_EXIT_PRECONDITION_ERROR, [])
    assert item.id in capsys.readouterr().err
