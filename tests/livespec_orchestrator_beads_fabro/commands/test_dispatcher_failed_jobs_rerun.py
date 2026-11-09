"""Classifier coverage for merge-poll's bounded failed-jobs re-run."""

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan


def test_classifies_teardown_only_job_from_failed_steps() -> None:
    module_path = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
        "_dispatcher_failed_jobs_rerun.py"
    )
    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    classified = module.classify_failed_job(
        job={
            "id": 12,
            "name": "check-coverage (nonroot)",
            "conclusion": "failure",
            "steps": [
                {"name": "Run checks", "conclusion": "success"},
                {"name": "Post Checkout", "conclusion": "failure"},
                {"name": "Stop containers", "conclusion": "failure"},
            ],
        },
        log="Executing the custom container implementation failed",
    )

    assert classified.kind == "runner-teardown"
    assert classified.evidence == (
        "failed teardown steps: Post Checkout, Stop containers",
        "log: container implementation failed",
    )


def test_classifies_kill_and_timeout_even_when_pytest_was_running() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )

    oom = module.classify_failed_job(
        job={"conclusion": "failure"},
        log="pytest tests/test_api.py::test_value\nProcess oom-killed after exceeded memory limit",
    )
    timeout = module.classify_failed_job(
        job={"conclusion": "timed_out"},
        log="pytest tests/test_api.py::test_value\nJob exceeded the maximum execution time",
    )

    assert oom.kind == "oom-kill"
    assert timeout.kind == "job-timeout"


def test_classifies_a_pytest_assertion_without_kill_or_timeout_as_unattributed() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )

    classified = module.classify_failed_job(
        job={"conclusion": "failure", "steps": [{"name": "Run tests", "conclusion": "failure"}]},
        log="FAILED tests/test_api.py::test_value - AssertionError",
    )

    assert classified.kind == "unattributed"
    assert classified.evidence == ()


def test_classifies_log_only_teardown_and_malformed_steps_conservatively() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )

    teardown = module.classify_failed_job(
        job={
            "conclusion": "failure",
            "steps": [{"name": "Post Checkout", "conclusion": "success"}],
        },
        log="container implementation failed",
    )
    malformed = module.classify_failed_job(
        job={"conclusion": "failure", "steps": {}},
        log="ordinary failure",
    )

    assert teardown.kind == "runner-teardown"
    assert malformed.kind == "unattributed"


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


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def test_does_not_rerun_when_an_oom_log_names_a_touched_test(tmp_path: Path) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    runner = _Runner(
        queue=[
            _ok(
                stdout=json.dumps(
                    {"jobs": [{"databaseId": 12, "name": "ci", "conclusion": "failure"}]}
                )
            ),
            _ok(stdout="FAILED tests/test_api.py::test_value\noom-kill"),
            _ok(stdout="tests/test_api.py\n"),
        ]
    )

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=_Journal(),
    )

    assert rerun is None
    assert ["gh", "run", "rerun", "42", "--failed"] not in runner.calls


def test_rejected_rerun_consumes_the_single_attempt_and_journals_reason(
    tmp_path: Path, monkeypatch
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    runner = _Runner(
        queue=[
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
            CommandResult(exit_code=1, stdout="", stderr="forge rejected"),
        ]
    )
    journal = _Journal()
    monkeypatch.setattr(module, "file_flake_item", lambda **_: "must not file")

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
    )

    assert rerun is not None and rerun.requested is False
    assert journal.records[-1]["failure_reason"] == "forge rejected"


def test_declines_unreadable_jobs_logs_and_changed_files(tmp_path: Path) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    failure = (
        module.TerminalCheckFailure(name="ci", details_url="https://x/actions/runs/42/job/12"),
    )
    cases = (
        [_ok(stdout="not json")],
        [_ok(stdout="[]")],
        [_ok(stdout="{}")],
        [_ok(stdout=json.dumps({"jobs": {}}))],
        [_ok(stdout=json.dumps({"jobs": []}))],
        [_ok(stdout=json.dumps({"jobs": [{"conclusion": "failure"}]}))],
        [
            _ok(
                stdout=json.dumps(
                    {"jobs": [{"databaseId": 12, "name": "ci", "conclusion": "failure"}]}
                )
            ),
            CommandResult(exit_code=1, stdout="", stderr="log unavailable"),
        ],
        [
            _ok(
                stdout=json.dumps(
                    {"jobs": [{"databaseId": 12, "name": "ci", "conclusion": "failure"}]}
                )
            ),
            _ok(stdout="pytest tests/test_api.py::test_value\noom-kill"),
            CommandResult(exit_code=1, stdout="", stderr="diff unavailable"),
        ],
    )

    for queue in cases:
        rerun = module.attempt_failed_jobs_rerun(
            failed=module.FailedRequiredChecks(
                names=["ci"], failures=failure, pr_number=7, pr_head="abc123"
            ),
            plan=_plan(repo=tmp_path),
            runner=_Runner(queue=queue),
            journal=_Journal(),
        )

        assert rerun is None


def test_filing_records_a_governed_repository_work_item(tmp_path: Path) -> None:
    filing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_filing"
    )
    (tmp_path / ".beads").mkdir()
    runner = _Runner(queue=[_ok()])

    failure = filing.file_flake_item(
        run_id="42",
        jobs=(("ci", "runner-teardown", ("failed teardown steps: Post Checkout",)),),
        plan=_plan(repo=tmp_path),
        runner=runner,
    )

    assert failure is None
    assert runner.calls == [
        [
            "bd",
            "create",
            "--type",
            "bug",
            "--title",
            "Flake: failed jobs re-run 42",
            "--description",
            "livespec-merge-poll-failed-jobs-rerun\nworkflow-run: 42\njob: ci\n"
            "class: runner-teardown\nevidence: failed teardown steps: Post Checkout",
        ]
    ]


def test_filing_failure_and_missing_pointer_are_reported(tmp_path: Path) -> None:
    filing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_filing"
    )
    runner = _Runner(queue=[])

    assert (
        filing.file_flake_item(run_id="42", jobs=(), plan=_plan(repo=tmp_path), runner=runner)
        == "beads pointer unavailable"
    )

    (tmp_path / ".beads").mkdir()
    runner.queue.append(CommandResult(exit_code=1, stdout="", stderr="store unavailable"))
    assert (
        filing.file_flake_item(run_id="42", jobs=(), plan=_plan(repo=tmp_path), runner=runner)
        == "store unavailable"
    )


def test_declines_when_one_of_several_failed_jobs_is_unattributed(tmp_path: Path) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    runner = _Runner(
        queue=[
            _ok(
                stdout=json.dumps(
                    {
                        "jobs": [
                            {"databaseId": 12, "name": "ci", "conclusion": "failure"},
                            {"databaseId": 13, "name": "lint", "conclusion": "failure"},
                        ]
                    }
                )
            ),
            _ok(stdout="oom-kill"),
            _ok(stdout="FAILED tests/test_other.py::test_value"),
        ]
    )

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci", "lint"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
                module.TerminalCheckFailure(
                    name="lint", details_url="https://x/actions/runs/42/job/13"
                ),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=_Journal(),
    )

    assert rerun is None
    assert ["gh", "run", "rerun", "42", "--failed"] not in runner.calls
    assert not any(call[:2] == ["bd", "create"] for call in runner.calls)


def test_declines_when_failures_name_no_single_workflow_run(tmp_path: Path) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    runner = _Runner(queue=[])

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci", "lint", "docs"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
                module.TerminalCheckFailure(
                    name="lint", details_url="https://x/actions/runs/43/job/13"
                ),
                module.TerminalCheckFailure(name="docs", details_url=None),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=_Journal(),
    )

    assert rerun is None
    assert runner.calls == []


def test_requested_rerun_journals_each_job_files_one_item_and_records_prior_attempt(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    (tmp_path / ".beads").mkdir()
    runner = _Runner(
        queue=[
            _ok(
                stdout=json.dumps(
                    {
                        "attempt": 1,
                        "jobs": [{"databaseId": 12, "name": "ci", "conclusion": "failure"}],
                    }
                )
            ),
            _ok(stdout="out of memory\nFAILED tests/test_untouched.py::test_value"),
            _ok(stdout="src/module.py\n"),
            _ok(),
            _ok(),
        ]
    )
    journal = _Journal()

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
    )

    assert rerun == module.FailedJobsRerun(workflow_run="42", requested=True, prior_attempt=1)
    row = next(r for r in journal.records if r["stage"] == "merge-poll-failed-jobs-rerun")
    assert row["workflow_run"] == "42"
    assert row["pr_head"] == "abc123"
    assert row["outcome"] == "requested"
    assert row["failed_jobs"] == [
        {"name": "ci", "class": "oom-kill", "evidence": ("oom-kill: out of memory",)}
    ]
    assert len([call for call in runner.calls if call[:2] == ["bd", "create"]]) == 1


def test_a_failed_flake_filing_is_journaled_and_does_not_undo_the_rerun(tmp_path: Path) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    runner = _Runner(
        queue=[
            _ok(
                stdout=json.dumps(
                    {"jobs": [{"databaseId": 12, "name": "ci", "conclusion": "failure"}]}
                )
            ),
            _ok(stdout="oom-kill"),
            _ok(),
            _ok(),
        ]
    )
    journal = _Journal()

    rerun = module.attempt_failed_jobs_rerun(
        failed=module.FailedRequiredChecks(
            names=["ci"],
            failures=(
                module.TerminalCheckFailure(
                    name="ci", details_url="https://x/actions/runs/42/job/12"
                ),
            ),
            pr_number=7,
            pr_head="abc123",
        ),
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
    )

    assert rerun is not None and rerun.requested is True
    assert rerun.prior_attempt == 1
    assert journal.records[-1]["outcome"] == "failed"
    assert journal.records[-1]["failure_reason"] == "beads pointer unavailable"


def test_filing_refuses_a_description_carrying_a_template_opener(tmp_path: Path) -> None:
    filing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_filing"
    )
    (tmp_path / ".beads").mkdir()
    runner = _Runner(queue=[])

    reason = filing.file_flake_item(
        run_id="42",
        jobs=(("{{ job }}", "oom-kill", ("oom-kill: out of memory",)),),
        plan=_plan(repo=tmp_path),
        runner=runner,
    )

    assert reason is not None and reason.startswith("template opener present")
    assert runner.calls == []
