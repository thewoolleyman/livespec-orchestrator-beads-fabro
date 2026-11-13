"""The engine takes the pre-merge runtime gate from the plan it was handed.

The gate used to be a seventh `run_dispatch` parameter, which the repository's
parameter-count lint refuses; it now rides the plan. These cases hold the engine's
side of that: a gate answering a `DispatchOutcome` ends the dispatch with exactly
that outcome BEFORE any merge is armed, and a gate with nothing to say -- absent,
`None`, or an answer that is not an outcome -- leaves the ordinary merge path
untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

_ITEM_ID = "bd-ib-z2y4ca"
_PR_NUMBER = 7
_GATE_STAGE = "pre-merge-convergence"


@dataclass(kw_only=True)
class _Runner:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "number": _PR_NUMBER,
                    "state": "OPEN",
                    "autoMergeRequest": None,
                    "mergeStateStatus": "CLEAN",
                    "mergeCommit": None,
                    "statusCheckRollup": [],
                }
            ),
            stderr="",
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    def launch(self, *, plan: DispatchPlan, runner: object, journal: object) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(command=CommandResult(exit_code=0, stdout="", stderr=""))


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
        merge_hold=False,
    )


def _dispatch(*, plan: DispatchPlan, runner: _Runner) -> DispatchOutcome:
    return run_dispatch(
        plan=plan,
        runner=runner,
        journal=_Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=_Launcher(),
    )


def test_a_gate_outcome_on_the_plan_ends_the_dispatch_before_any_merge_is_armed(
    tmp_path: Path,
) -> None:
    asked: list[dict[str, object]] = []
    breach = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage=_GATE_STAGE,
        pr_number=_PR_NUMBER,
        merge_sha=None,
        detail="LIVESPEC_NON_CONVERGED: a ceiling was exceeded",
        fabro_run_id=None,
    )

    def gate(**kwargs: object) -> DispatchOutcome:
        asked.append(kwargs)
        return breach

    runner = _Runner()

    outcome = _dispatch(plan=replace(_plan(repo=tmp_path), pre_merge_gate=gate), runner=runner)

    assert outcome == breach
    assert asked == [{"pr_number": _PR_NUMBER, "run_id": None}]
    assert not [argv for argv in runner.calls if argv[:3] == ["gh", "pr", "merge"]]


def test_a_plan_with_no_gate_reaches_the_merge_hold_with_the_pull_request_it_read(
    tmp_path: Path,
) -> None:
    runner = _Runner()

    outcome = _dispatch(plan=_plan(repo=tmp_path), runner=runner)

    assert outcome.stage != _GATE_STAGE
    assert outcome.pr_number == _PR_NUMBER
    assert runner.calls


@pytest.mark.parametrize("answer", [None, "no verdict"])
def test_a_gate_with_no_outcome_changes_nothing_about_the_ordinary_path(
    tmp_path: Path, answer: object
) -> None:
    ungated = _dispatch(plan=_plan(repo=tmp_path), runner=_Runner())
    runner = _Runner()

    outcome = _dispatch(
        plan=replace(_plan(repo=tmp_path), pre_merge_gate=lambda **_: answer), runner=runner
    )

    assert outcome == ungated
