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
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
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


def _jobs() -> str:
    return json.dumps(
        {
            "attempt": 1,
            "jobs": [
                {
                    "databaseId": 12,
                    "name": "ci",
                    "conclusion": "failure",
                    "steps": [{"name": "Post Checkout", "conclusion": "failure"}],
                }
            ],
        }
    )


def _merged() -> str:
    return json.dumps({"number": 7, "state": "MERGED", "mergeCommit": {"oid": "cafe06"}})


def _after_first_rerun() -> list[CommandResult]:
    return [
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout=_jobs()),
        _ok(stdout="container implementation failed"),
        _ok(),
        _ok(),
    ]


def _run(*, queue: list[CommandResult], tmp_path: Path, attempts: int):
    runner = _Runner(queue=queue)
    journal = _Journal()
    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.5),
    )
    return outcome, runner, journal


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
    queue = [
        *_after_first_rerun(),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout=json.dumps({"attempt": 2})),
    ]

    outcome, runner, journal = _run(queue=queue, tmp_path=tmp_path, attempts=2)

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "required check failed terminally: ci" in outcome.detail
    assert [call for call in runner.calls if call[:3] == ["gh", "run", "rerun"]] == [
        ["gh", "run", "rerun", "42", "--failed"]
    ]
    rows = [r for r in journal.records if r.get("stage") == "merge-poll-failed-jobs-rerun"]
    assert [(r["workflow_run"], r["outcome"]) for r in rows] == [
        ("42", "requested"),
        ("42", "required-check-failed"),
    ]


def test_await_merge_disregards_the_rerun_attempt_the_forge_still_reports(tmp_path: Path) -> None:
    queue = [
        *_after_first_rerun(),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout=json.dumps({"attempt": 1})),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        CommandResult(exit_code=1, stdout="", stderr="forge unavailable"),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout="not json"),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout="[]"),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout=json.dumps({"attempt": "2"})),
        _ok(stdout=_view()),
        _ok(stdout=_required()),
        _ok(stdout=json.dumps({"attempt": 3})),
    ]

    outcome, runner, _ = _run(queue=queue, tmp_path=tmp_path, attempts=7)

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert queue == []
    assert len([call for call in runner.calls if call[:3] == ["gh", "run", "rerun"]]) == 1


def test_await_merge_journals_a_merge_of_the_rerun_attempt(tmp_path: Path) -> None:
    queue = [*_after_first_rerun(), _ok(stdout=_merged())]

    merged, _, journal = _run(queue=queue, tmp_path=tmp_path, attempts=2)

    assert not isinstance(merged, DispatchOutcome)
    assert merged is not None
    rows = [r for r in journal.records if r.get("stage") == "merge-poll-failed-jobs-rerun"]
    assert [(r["workflow_run"], r["outcome"]) for r in rows] == [
        ("42", "requested"),
        ("42", "merged"),
    ]


def test_await_merge_does_not_rerun_on_the_last_poll_of_the_budget(tmp_path: Path) -> None:
    queue = [_ok(stdout=_view()), _ok(stdout=_required())]

    outcome, runner, journal = _run(queue=queue, tmp_path=tmp_path, attempts=1)

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert not any(call[:3] == ["gh", "run", "rerun"] for call in runner.calls)
    assert not any(r.get("stage") == "merge-poll-failed-jobs-rerun" for r in journal.records)


def test_await_merge_counts_a_journaled_rerun_of_the_same_head_across_a_restart(
    tmp_path: Path,
) -> None:
    journal_file = tmp_path / "journal.jsonl"
    prior = {
        "work_item_id": "x-1",
        "stage": "merge-poll-failed-jobs-rerun",
        "workflow_run": "42",
        "pr_head": "abc123",
        "outcome": "rejected",
    }
    journal_file.write_text(json.dumps(prior) + "\n", encoding="utf-8")
    failing_view = json.loads(_view())
    failing_view["headRefOid"] = "abc123"
    runner = _Runner(
        queue=[_ok(stdout=json.dumps(failing_view)), _ok(stdout=_required()), _ok(), _ok()]
    )

    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=JournalFile(path=journal_file),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert not any(call[:3] == ["gh", "run", "view"] for call in runner.calls)
    assert not any(call[:3] == ["gh", "run", "rerun"] for call in runner.calls)
