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

# A DECLARED janitor-core pin: an undeclared one, or an unresolved default
# branch, degrades the post-merge flow before any of these cases is reached.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
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


def _venue_resolution() -> list[CommandResult]:
    """The ONE venue read between pull-primary and the preclean: the probe
    confirming the tip contains the merge. The branch it names is read off the
    plan's resolved integration contract rather than re-probed here."""
    return [_ok()]


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

    view = confirm_pr(plan=_plan(repo=tmp_path), runner=runner, journal=journal, hold="unheld")

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


# Entries copied verbatim from `gh pr view 3913 --json statusCheckRollup`: the
# real shape carries exactly these keys and never `isRequired` or `required`.
_REAL_CI_GREEN_FAILURE: dict[str, object] = {
    "__typename": "CheckRun",
    "completedAt": "2026-10-29T05:10:30Z",
    "conclusion": "FAILURE",
    "detailsUrl": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/actions/runs/40821372772/job/123275870309",
    "name": "ci-green",
    "startedAt": "2026-10-29T05:10:28Z",
    "status": "COMPLETED",
    "workflowName": "CI",
}
_REAL_COVERAGE_FAILURE: dict[str, object] = {
    "__typename": "CheckRun",
    "completedAt": "2026-10-29T05:10:08Z",
    "conclusion": "FAILURE",
    "detailsUrl": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/actions/runs/40821372772/job/123274367716",
    "name": "check-per-file-coverage (root)",
    "startedAt": "2026-10-29T05:05:44Z",
    "status": "COMPLETED",
    "workflowName": "CI",
}
_REAL_LINT_SUCCESS: dict[str, object] = {
    "__typename": "CheckRun",
    "completedAt": "2026-10-29T05:06:08Z",
    "conclusion": "SUCCESS",
    "detailsUrl": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/actions/runs/40821372772/job/123274367818",
    "name": "check-lint (root)",
    "startedAt": "2026-10-29T05:05:48Z",
    "status": "COMPLETED",
    "workflowName": "CI",
}


def _required_checks_graphql(*, required: list[str]) -> str:
    """The forge's `isRequired(pullRequestNumber:)` answer: every context, flagged."""
    names = ["enable-auto-merge", "check-lint (root)", "check-per-file-coverage (root)", "ci-green"]
    nodes = [
        {"__typename": "CheckRun", "name": name, "isRequired": name in required} for name in names
    ]
    rollup = {"contexts": {"nodes": nodes}}
    pull_request = {"commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]}}
    return json.dumps({"data": {"repository": {"pullRequest": pull_request}}})


def test_await_merge_fails_fast_when_ci_green_failed_and_rollup_has_no_required_key(
    tmp_path: Path,
) -> None:
    rollup = [_REAL_LINT_SUCCESS, _REAL_COVERAGE_FAILURE, _REAL_CI_GREEN_FAILURE]
    assert all("isRequired" not in entry and "required" not in entry for entry in rollup)
    runner = Runner(
        queue=[
            _ok(stdout=_pr_json(merge_state="BLOCKED", checks=rollup)),
            _ok(stdout=_required_checks_graphql(required=["ci-green"])),
        ]
    )

    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.5),
    )

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "required check failed terminally: ci-green" in outcome.detail
    assert "resolve-blocked:x-1:ready" in outcome.detail
    assert "resume --item x-1" in outcome.detail


def test_await_merge_reads_required_checks_from_the_forge_not_the_rollup(
    tmp_path: Path,
) -> None:
    runner = Runner(
        queue=[
            _ok(stdout=_pr_json(merge_state="BLOCKED", checks=[_REAL_CI_GREEN_FAILURE])),
            _ok(stdout=_required_checks_graphql(required=["ci-green"])),
        ]
    )

    await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.5),
    )

    required_argv, required_cwd = runner.calls[1]
    assert required_argv[:3] == ["gh", "api", "graphql"]
    assert any("isRequired(pullRequestNumber: $number)" in part for part in required_argv)
    assert "number=7" in required_argv
    assert required_cwd == tmp_path


def test_await_merge_keeps_polling_when_the_only_failed_check_is_not_required(
    tmp_path: Path,
) -> None:
    runner = Runner(
        queue=[
            _ok(stdout=_pr_json(merge_state="BLOCKED", checks=[_REAL_COVERAGE_FAILURE])),
            _ok(stdout=_required_checks_graphql(required=["ci-green"])),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe04")),
        ]
    )
    naps: list[float] = []

    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=naps.append,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert not isinstance(merged, DispatchOutcome)
    assert merged is not None
    assert merged.merge_sha == "cafe04"
    assert naps == [0.5]


def test_await_merge_keeps_polling_when_the_required_checks_cannot_be_read(
    tmp_path: Path,
) -> None:
    runner = Runner(
        queue=[
            _ok(stdout=_pr_json(merge_state="BLOCKED", checks=[_REAL_CI_GREEN_FAILURE])),
            _err(stderr="GraphQL: Resource not accessible by integration"),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
        ]
    )

    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert not isinstance(merged, DispatchOutcome)
    assert merged is not None
    assert merged.merge_sha == "cafe05"


def test_await_merge_does_not_treat_an_open_fallback_as_merged(tmp_path: Path) -> None:
    runner = Runner(
        queue=[
            _err(stderr="GraphQL: Resource not accessible by integration"),
            _ok(stdout=_pr_json(state="OPEN")),
        ]
    )

    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.5),
    )

    assert merged is None
    assert "statusCheckRollup" in runner.calls[0][0][-1]
    assert "statusCheckRollup" not in runner.calls[1][0][-1]


def test_post_merge_runs_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = Runner(queue=[_ok(), *_venue_resolution(), *[_ok() for _ in range(8)]])
    merged = confirm_pr(
        plan=_plan(repo=tmp_path),
        runner=Runner(queue=[_ok(stdout=_pr_json(state="MERGED", sha="cafe06"))]),
        journal=Journal(),
        hold="unheld",
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
        if argv
        == [
            "mise",
            "exec",
            "--",
            "just",
            "check-no-workflow-edits",
            "install-worktree-pack",
            "check",
        ]
    ]
    assert janitor_calls == [
        (
            [
                "mise",
                "exec",
                "--",
                "just",
                "check-no-workflow-edits",
                "install-worktree-pack",
                "check",
            ],
            tmp_path / "janitor-co",
        )
    ]
    # The janitor's env DELTA: the core-plugin root it adds, and the
    # dispatcher's factory route and invoker attribution removed, so the check
    # verdict is about the merge rather than about how this dispatch was routed
    # and attributed.
    assert runner.envs[-2] == {
        "LIVESPEC_CORE_PLUGIN_ROOT": str(tmp_path / "janitor-co-livespec-core" / ".claude-plugin"),
        "LIVESPEC_FABRO_FACTORY": None,
        "LIVESPEC_INVOKER": None,
    }


def test_post_merge_degrades_when_checkout_provisioning_fails(tmp_path: Path) -> None:
    runner = Runner(
        queue=[
            _ok(),
            *_venue_resolution(),
            _err(stderr="not a working tree"),
            _err(stderr="disk full"),
        ]
    )
    merged = confirm_pr(
        plan=_plan(repo=tmp_path),
        runner=Runner(queue=[_ok(stdout=_pr_json(state="MERGED", sha="cafe08"))]),
        journal=Journal(),
        hold="unheld",
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
