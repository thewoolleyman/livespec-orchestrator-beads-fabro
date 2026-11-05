"""Bounded merge-poll recovery after a failed-jobs rerun."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import await_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan


@dataclass(kw_only=True)
class _Runner:
    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = cwd, timeout_seconds
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _plan(*, repo: Path):
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
    )


def _view() -> str:
    return json.dumps(
        {
            "number": 7,
            "state": "OPEN",
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": "BLOCKED",
            "statusCheckRollup": [
                {
                    "name": "ci",
                    "conclusion": "FAILURE",
                    "detailsUrl": "https://x/actions/runs/42/job/12",
                }
            ],
        }
    )


def _required() -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "commits": {
                            "nodes": [
                                {
                                    "commit": {
                                        "statusCheckRollup": {
                                            "contexts": {
                                                "nodes": [{"name": "ci", "isRequired": True}]
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def test_await_merge_blocks_the_rerun_attempt_without_a_second_request(tmp_path: Path) -> None:
    runner = _Runner(
        queue=[
            _ok(stdout=_view()),
            _ok(stdout=_required()),
            _ok(
                stdout=json.dumps(
                    {
                        "jobs": [
                            {
                                "databaseId": 12,
                                "name": "ci",
                                "conclusion": "failure",
                                "steps": [{"name": "Post Checkout", "conclusion": "failure"}],
                            }
                        ]
                    }
                )
            ),
            _ok(stdout="container implementation failed"),
            _ok(),
            _ok(),
            _ok(stdout=_view()),
            _ok(stdout=_required()),
        ]
    )

    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=_Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    rerun_call = next(call for call in runner.calls if call[:4] == ["gh", "run", "rerun", "42"])
    assert rerun_call == ["gh", "run", "rerun", "42", "--failed"]
    assert len([call for call in runner.calls if call[:3] == ["gh", "run", "rerun"]]) == 1
