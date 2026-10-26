"""The real-origin stale-publish-branch recovery journey for Scenario 144."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop,
    _dispatcher_publish_branch_reclaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PUBLISH_BRANCH_RECLAIM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-hfi52b"
_RUN_ID = "01M5RECLAIM000000000000000"
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_WORKFLOW_TOML = '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
_GRAPH = (
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
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Integration Test",
    "GIT_AUTHOR_EMAIL": "integration@example.invalid",
    "GIT_COMMITTER_NAME": "Integration Test",
    "GIT_COMMITTER_EMAIL": "integration@example.invalid",
}


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Use the real dispatch path over a fresh hermetic ledger tenant."""
    scratch = tmp_path_factory.mktemp("publish-branch-reclaim")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:publish-branch-reclaim")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    for name in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(name, raising=False)
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


def _seed_item() -> WorkItem:
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Reclaim a dead publish branch",
        description=(
            "Re-dispatch the interrupted work.\n"
            "\n"
            "## Definition of Done\n"
            "\n"
            "- The stale publish branch is reclaimed before launch.\n"
            "\n"
            "References: ## Scenario 144\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-26T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The stale publish branch is reclaimed before launch.",
    )
    append_work_item(path=_config(), item=item)
    return item


def _git(*argv: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *argv], cwd=cwd, check=True, capture_output=True, env=_GIT_ENV, text=True
    )
    return completed.stdout.strip()


@dataclass(kw_only=True)
class _OriginRunner:
    """Runs origin reads for real and translates the forge ref API onto that origin."""

    origin: Path
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_kwargs: object
    ) -> CommandResult:
        del timeout_seconds
        self.calls.append(argv)
        if argv[:2] == ["git", "ls-remote"]:
            completed = subprocess.run(
                argv, check=False, cwd=cwd, capture_output=True, env=_GIT_ENV, text=True
            )
            return CommandResult(
                exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
            )
        if argv[1:4] == ["ps", "-a", "--json"]:
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        if argv[:4] == ["gh", "api", "--method", "POST"]:
            fields = [value for value in argv if value.startswith(("ref=", "sha="))]
            ref = next(value.removeprefix("ref=") for value in fields if value.startswith("ref="))
            sha = next(value.removeprefix("sha=") for value in fields if value.startswith("sha="))
            _ = _git("--git-dir", str(self.origin), "update-ref", ref, sha, cwd=cwd)
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:4] == ["gh", "api", "--method", "DELETE"]:
            endpoint = argv[-1]
            ref = "refs/" + endpoint.partition("/git/refs/")[2]
            _ = _git("--git-dir", str(self.origin), "update-ref", "-d", ref, cwd=cwd)
            return CommandResult(exit_code=0, stdout="", stderr="")
        raise AssertionError(f"unexpected dispatch reclaim command: {argv}")


def _world(*, tmp_path: Path) -> tuple[Path, Path, Path, str]:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    _ = _git("init", "--bare", str(origin), cwd=tmp_path)
    _ = _git("init", str(repo), cwd=tmp_path)
    _ = _git("config", "user.name", "Integration Test", cwd=repo)
    _ = _git("config", "user.email", "integration@example.invalid", cwd=repo)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {},
                },
            }
        ),
        encoding="utf-8",
    )
    workflow = repo / "workflow.toml"
    _ = workflow.write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (repo / "graph.toml").write_text(_GRAPH, encoding="utf-8")
    (repo / "dead-run.txt").write_text("published by dead run\n", encoding="utf-8")
    _ = _git("add", ".", cwd=repo)
    _ = _git("commit", "-m", "dead publish", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo)
    _ = _git("remote", "add", "origin", str(origin), cwd=repo)
    _ = _git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=repo)
    return origin, repo, workflow, head


def _recording_run_dispatch(*, launches: list[str]) -> Callable[..., DispatchOutcome]:
    """Stand in only for the Fabro launch after the real dispatch path admits."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        launches.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="recorded launch",
        )

    return _run_dispatch


def test_scenario144_reclaims_a_dead_publish_branch_on_a_real_origin_and_records_its_preservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 144: preserve first, delete second, then permit a plain re-dispatch."""
    _ = _seed_item()
    origin, repo, workflow, dead_head = _world(tmp_path=tmp_path)
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID, "run_id": _RUN_ID})
    runner = _OriginRunner(origin=origin)
    launches: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _recording_run_dispatch(launches=launches)
    )
    monkeypatch.setattr(
        _dispatcher_publish_branch_reclaim,
        "ShellCommandRunner",
        lambda: runner,
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    preserved = preserved_publish_ref(work_item_id=_ITEM_ID, head=dead_head)
    assert exit_code == 0
    assert launches == [_ITEM_ID]
    assert (
        materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status == "active"
    )
    assert _git("--git-dir", str(origin), "rev-parse", preserved, cwd=repo) == dead_head
    absent = subprocess.run(
        [
            "git",
            "--git-dir",
            str(origin),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        check=False,
        env=_GIT_ENV,
    )
    assert absent.returncode == 1
    record = next(
        row
        for row in read_journal_records(journal_path=journal.path)
        if row["stage"] == PUBLISH_BRANCH_RECLAIM_STAGE
    )
    assert record["preserved_ref"] == preserved
    assert record["head"] == dead_head


def test_reclaim_runner_rejects_an_unrecognized_command(tmp_path: Path) -> None:
    """The reclaim fake fails loudly if the production command grows a new boundary."""
    with pytest.raises(AssertionError, match="unexpected dispatch reclaim command"):
        _OriginRunner(origin=tmp_path).run(argv=["unexpected"], cwd=tmp_path, timeout_seconds=1)
