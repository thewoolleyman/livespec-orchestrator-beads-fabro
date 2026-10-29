"""The janitor provisions livespec core OUTSIDE the adopter's checkout.

An untracked `.livespec-core/` inside the fresh janitor checkout is scanned by
the governed repository's own formatter and lint gates, which fail the
post-merge janitor on a tree whose committed content is clean. The provisioned
core therefore lives beside the checkout, never in it, and the journal row for
the provisioning names where it was placed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_core_checkout_path,
    janitor_core_clone_argv,
    janitor_worktree_add_argv,
)

_MERGE_SHA = "16fe3ac"


def _config(*, core_repo: str | None = None) -> str:
    compat: dict[str, str] = {"pinned": "master"}
    if core_repo is not None:
        compat["core_repo"] = core_repo
    return json.dumps({"livespec-orchestrator-beads-fabro": {"compat": compat}})


def _plan(*, repo: Path, config_text: str) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=config_text,
        default_branch="main",
    )


@dataclass(kw_only=True)
class _Runner:
    cloned_into_a_clear_path: list[bool] = field(default_factory=list)
    plan: DispatchPlan

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        if argv[:2] == ["git", "clone"]:
            self.cloned_into_a_clear_path.append(not self.plan.janitor_core_checkout.exists())
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _merged() -> PrView:
    return PrView(
        number=7,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha=_MERGE_SHA,
    )


def _git(*, cwd: Path, args: list[str]) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def test_the_provisioned_core_sits_outside_the_janitor_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "janitor-co"

    core = janitor_core_checkout_path(janitor_checkout=checkout)

    assert not core.is_relative_to(checkout)
    assert core.parent == checkout.parent


def test_a_clone_of_core_leaves_the_checkout_status_empty(tmp_path: Path) -> None:
    core_remote = tmp_path / "core-remote"
    core_remote.mkdir()
    _git(cwd=core_remote, args=["init", "-q", "-b", "master"])
    (core_remote / "unformatted.json").write_text('{"a":1}', encoding="utf-8")
    _git(cwd=core_remote, args=["add", "."])
    _git(cwd=core_remote, args=["commit", "-q", "-m", "core"])
    target = tmp_path / "target"
    target.mkdir()
    _git(cwd=target, args=["init", "-q", "-b", "main"])
    (target / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(cwd=target, args=["add", "."])
    _git(cwd=target, args=["commit", "-q", "-m", "target"])
    plan = _plan(repo=target, config_text=_config(core_repo=str(core_remote)))

    _ = subprocess.run(
        janitor_worktree_add_argv(plan=plan, tip="main"), check=True, capture_output=True
    )
    _ = subprocess.run(janitor_core_clone_argv(plan=plan), check=True, capture_output=True)

    assert plan.janitor_core_checkout.joinpath("unformatted.json").is_file()
    assert _git(cwd=plan.janitor_checkout, args=["status", "--porcelain"]) == ""


def test_the_provisioning_row_names_where_the_core_was_placed(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path, config_text=_config())
    journal = _Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=_Runner(plan=plan),
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    rows = [row for row in journal.records if row["stage"] == "janitor-core-provision"]
    assert len(rows) == 1
    assert rows[0]["core_path"] == str(plan.janitor_core_checkout)


def test_a_stale_core_is_cleared_before_the_clone_and_removed_after_a_green_run(
    tmp_path: Path,
) -> None:
    plan = _plan(repo=tmp_path, config_text=_config())
    stale = plan.janitor_core_checkout
    stale.mkdir(parents=True)
    (stale / "left-by-a-crashed-dispatch.txt").write_text("stale", encoding="utf-8")
    runner = _Runner(plan=plan)

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=_Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert runner.cloned_into_a_clear_path == [True]
    assert not stale.exists()
