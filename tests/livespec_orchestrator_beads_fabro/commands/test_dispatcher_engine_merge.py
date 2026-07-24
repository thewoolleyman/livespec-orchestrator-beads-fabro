"""Tests for the Dispatcher's merge and post-merge engine slice."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    await_merge,
    confirm_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
    )


@dataclass(kw_only=True)
class Runner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    envs: list[dict[str, str] | None] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        self.envs.append(env)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _err(stderr: str = "boom") -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def _pr_json(
    *,
    state: str = "OPEN",
    armed: bool = True,
    merge_state: str = "CLEAN",
    sha: str | None = None,
    checks: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "number": 7,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": sha} if sha is not None else None,
            "statusCheckRollup": checks if checks is not None else [],
        }
    )


def test_confirm_pr_arms_auto_merge_when_needed(tmp_path: Path) -> None:
    runner = Runner(queue=[_ok(stdout=_pr_json(armed=False)), _ok(), _ok(stdout=_pr_json())])
    journal = Journal()

    view = confirm_pr(plan=_plan(repo=tmp_path), runner=runner, journal=journal)

    assert view is not None
    assert view.auto_merge_armed is True
    assert runner.calls[1][0][:3] == ["gh", "pr", "merge"]
    assert [record["stage"] for record in journal.records] == [
        "pr-view",
        "pr-arm-fallback",
        "pr-view",
    ]


def test_await_merge_updates_behind_branch_then_returns_merged(tmp_path: Path) -> None:
    runner = Runner(
        queue=[
            _ok(stdout=_pr_json(merge_state="BEHIND")),
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe04")),
        ]
    )
    journal = Journal()
    naps: list[float] = []

    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
        sleep=naps.append,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert not isinstance(merged, DispatchOutcome)
    assert merged is not None
    assert merged.merge_sha == "cafe04"
    assert runner.calls[1][0] == ["gh", "pr", "update-branch", "7"]
    assert naps == [0.5]


def test_await_merge_fails_fast_on_terminal_required_check(tmp_path: Path) -> None:
    runner = Runner(
        queue=[
            _ok(
                stdout=_pr_json(
                    merge_state="BLOCKED",
                    checks=[
                        {"name": "check-coverage", "isRequired": True, "conclusion": "failure"},
                        {"name": "docs", "isRequired": False, "conclusion": "failure"},
                    ],
                )
            ),
        ]
    )

    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=80, interval_seconds=0.5),
    )

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert "check-coverage" in outcome.detail
    assert "docs" not in outcome.detail


def test_post_merge_runs_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = Runner(queue=[_ok() for _ in range(8)])
    merged = confirm_pr(
        plan=_plan(repo=tmp_path),
        runner=Runner(queue=[_ok(stdout=_pr_json(state="MERGED", sha="cafe06"))]),
        journal=Journal(),
    )
    assert merged is not None

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=merged,
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    janitor_calls = [
        (argv, cwd)
        for argv, cwd in runner.calls
        if argv == ["mise", "exec", "--", "just", "check-no-workflow-edits", "check"]
    ]
    assert janitor_calls == [
        (
            ["mise", "exec", "--", "just", "check-no-workflow-edits", "check"],
            tmp_path / "janitor-co",
        )
    ]
    assert runner.envs[-2] == {
        "LIVESPEC_CORE_PLUGIN_ROOT": str(
            tmp_path / "janitor-co" / ".livespec-core" / ".claude-plugin"
        )
    }


def test_post_merge_degrades_when_checkout_provisioning_fails(tmp_path: Path) -> None:
    runner = Runner(queue=[_ok(), _err(stderr="not a working tree"), _err(stderr="disk full")])
    merged = confirm_pr(
        plan=_plan(repo=tmp_path),
        runner=Runner(queue=[_ok(stdout=_pr_json(state="MERGED", sha="cafe08"))]),
        journal=Journal(),
    )
    assert merged is not None

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=merged,
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "DID NOT RUN" in outcome.detail
    assert "disk full" in outcome.detail
    assert "not a work-item failure" in outcome.detail
