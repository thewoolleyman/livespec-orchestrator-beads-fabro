"""Real-Git staging provenance; the actual hp engine remains host-captured proof."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight,
)


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(argv=["git", *args], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _ancestor_source(*, root: Path) -> tuple[Path, str, str]:
    origin = root / "origin.git"
    repo = root / "source"
    _git(repo=root, args=["init", "--bare", str(origin)])
    _git(repo=root, args=["init", "--initial-branch=master", str(repo)])
    _git(repo=repo, args=["config", "user.name", "Test User"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["remote", "add", "origin", str(origin)])
    (repo / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(repo=repo, args=["add", "tracked.txt"])
    _git(repo=repo, args=["commit", "-m", "source"])
    head = _git(repo=repo, args=["rev-parse", "HEAD"])
    (repo / "tracked.txt").write_text("advanced\n", encoding="utf-8")
    _git(repo=repo, args=["commit", "-am", "advance origin"])
    _git(repo=repo, args=["push", "origin", "master"])
    remote_head = _git(repo=repo, args=["rev-parse", "HEAD"])
    _git(repo=repo, args=["reset", "--hard", head])
    (repo / "uncommitted.txt").write_text("retain primary state\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text(
        '#!/bin/sh\nif [ "$(git rev-parse --git-dir)" = '
        '"$(git rev-parse --git-common-dir)" ]; then\n'
        "  echo 'livespec: refusing commit/push at primary checkout; use a worktree' >&2\n"
        "  exit 1\nfi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return repo, head, remote_head


@dataclass(kw_only=True)
class _EngineRunner:
    """Model only the engine's pre-run push, with REAL Git and the source hook."""

    launch_cwds: list[Path] = field(default_factory=list)
    launch_heads: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if argv[:2] == ["fabro", "run"]:
            self.launch_cwds.append(cwd)
            self.launch_heads.append(_git(repo=cwd, args=["rev-parse", "HEAD"]))
            branch = _git(repo=cwd, args=["symbolic-ref", "--short", "HEAD"])
            argv = ["git", "push", "origin", branch]
        return ShellCommandRunner().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_staged_run_journals_source_head_and_its_containing_origin_ref(*, tmp_path: Path) -> None:
    repo, head, remote_head = _ancestor_source(root=tmp_path)
    engine = _EngineRunner()
    # Positive control: the primary hook actually refuses the engine's push.
    refused = engine.run(argv=["fabro", "run"], cwd=repo, timeout_seconds=30)
    assert refused.exit_code != 0
    assert "refusing commit/push at primary checkout" in refused.stderr
    preflight = source_checkout_preflight(repo=repo, runner=engine)
    assert preflight.refusal is None
    # This assertion is the Red: a list of all refs is not a containment witness.
    assert preflight.record.get("origin_ref") == "origin/master"

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_source_staging"
    )
    journal = _Journal()
    root = tmp_path / ".worktrees"
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-urhjxd",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
        default_branch="master",
    )
    runner = module.SourceStagingRunner(
        inner=engine, plan=plan, journal=journal, worktree_root=root
    )
    result = runner.run(argv=["fabro", "run"], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    staged = next(row for row in journal.records if row["stage"] == "source-checkout-stage")
    assert staged["status"] == "passed"
    assert staged["head"] == head
    assert staged["origin_ref"] == "origin/master"
    assert staged["work_item_id"] == "bd-ib-urhjxd"
    checkout = engine.launch_cwds[-1]
    assert checkout.is_relative_to(root / repo.name)
    assert staged["worktree"] == str(checkout)
    assert engine.launch_heads[-1] == head
    _assert_cleanup(repo=repo, checkout=checkout, head=head, remote_head=remote_head)


def _assert_cleanup(*, repo: Path, checkout: Path, head: str, remote_head: str) -> None:
    assert not checkout.exists()
    assert _git(repo=repo, args=["rev-parse", "HEAD"]) == head
    assert _git(repo=repo, args=["symbolic-ref", "--short", "HEAD"]) == "master"
    assert (repo / "uncommitted.txt").read_text(encoding="utf-8") == "retain primary state\n"
    assert _git(repo=repo, args=["ls-remote", "--heads", "origin"]) == (
        f"{remote_head}\trefs/heads/master"
    )
    assert _git(repo=repo, args=["branch", "--format=%(refname:short)"]) == "master"
    assert _git(repo=repo, args=["worktree", "list", "--porcelain"]).count("worktree ") == 1
