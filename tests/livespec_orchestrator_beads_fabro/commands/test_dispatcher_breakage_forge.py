"""Cached GitHub reads of the breakage pass, through a fake `gh` on PATH."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    FailedJob,
    Run,
    failed_jobs,
    failing_tests,
    latest_completed_run,
)

_REPO = "repos/{owner}/{repo}"
_RUNS = "repos/{owner}/{repo}/actions/workflows/ci.yml/runs?branch=main&status=completed&per_page=1"
_JOBS = "repos/{owner}/{repo}/actions/runs/9/jobs?filter=latest&per_page=100"
_LOGS = "repos/{owner}/{repo}/actions/jobs/5/logs"
_RUN = Run(identifier=9, conclusion="failure", head_sha="abc", url="https://x/9")
_JOB = FailedJob(identifier=5, name="job", failed_step="step")
_GH = (
    f"#!{sys.executable}\n"
    "import json, os, sys\n"
    "answer = json.loads(os.environ['FAKE_GH_ANSWERS'])[sys.argv[-1]]\n"
    "sys.stdout.write(answer[1])\n"
    "sys.stderr.write(answer[2])\n"
    "sys.exit(answer[0])\n"
)


def _fake_gh(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answers: dict[str, tuple[int, str, str]]
) -> None:
    program = tmp_path / "bin" / "gh"
    program.parent.mkdir()
    _ = program.write_text(_GH, encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{program.parent}:/usr/bin:/bin")
    monkeypatch.setenv("FAKE_GH_ANSWERS", json.dumps(answers))


def _ok(*, body: object) -> tuple[int, str, str]:
    return 0, json.dumps(body), ""


_BRANCH = {_REPO: _ok(body={"default_branch": "main"})}
_RUN_RECORD = {
    "id": 9,
    "conclusion": "failure",
    "head_sha": "abc",
    "html_url": "https://x/9",
}


@pytest.mark.parametrize(
    ("answers", "expected_problem"),
    [
        ({_REPO: (1, "", "boom\n")}, "default branch: boom"),
        ({_REPO: (1, "out\n", "")}, "default branch: out"),
        ({_REPO: (4, "", "")}, "default branch: gh exited 4"),
        ({_REPO: (0, "{", "")}, "default branch: invalid JSON: "),
        ({_REPO: _ok(body=[1])}, "default branch: malformed response"),
        ({_REPO: _ok(body={})}, "default branch: response omitted default_branch"),
        ({**_BRANCH, _RUNS: (1, "", "nope")}, "workflow runs: nope"),
        ({**_BRANCH, _RUNS: _ok(body={"workflow_runs": ["x"]})}, "workflow runs: malformed run"),
        (
            {**_BRANCH, _RUNS: _ok(body={"workflow_runs": [{**_RUN_RECORD, "conclusion": None}]})},
            "workflow runs: incomplete run",
        ),
        (
            {**_BRANCH, _RUNS: _ok(body={"workflow_runs": [{**_RUN_RECORD, "id": "9"}]})},
            "workflow runs: incomplete run",
        ),
    ],
)
def test_latest_completed_run_reports_each_unreadable_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: dict[str, tuple[int, str, str]],
    expected_problem: str,
) -> None:
    """Scenario 313: an unreadable forge answer is reported, never read as green."""
    _fake_gh(tmp_path=tmp_path, monkeypatch=monkeypatch, answers=answers)

    run, problem = latest_completed_run(repo=tmp_path, workflow="ci.yml")

    assert run is None
    assert problem is not None
    assert problem.startswith(expected_problem)


@pytest.mark.parametrize(
    "runs_body",
    [{}, {"workflow_runs": []}, {"workflow_runs": "x"}, [1]],
)
def test_latest_completed_run_without_a_run_is_not_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs_body: object
) -> None:
    """Scenario 313: a workflow with no completed run files nothing and is not an error."""
    answers = {**_BRANCH, _RUNS: _ok(body=runs_body)}
    _fake_gh(tmp_path=tmp_path, monkeypatch=monkeypatch, answers=answers)

    assert latest_completed_run(repo=tmp_path, workflow="ci.yml") == (None, None)


def test_latest_completed_run_returns_the_newest_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 313: the run's head SHA, conclusion and URL are carried."""
    answers = {**_BRANCH, _RUNS: _ok(body={"workflow_runs": [_RUN_RECORD]})}
    _fake_gh(tmp_path=tmp_path, monkeypatch=monkeypatch, answers=answers)

    assert latest_completed_run(repo=tmp_path, workflow="ci.yml") == (_RUN, None)


def test_failed_jobs_names_each_failed_job_and_its_failing_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 313: one failed job per entry, with the first failing named step."""
    jobs = [
        "not-a-job",
        {"id": 1, "name": "green", "conclusion": "success"},
        {
            "id": 2,
            "name": "no-steps",
            "conclusion": "failure",
        },
        {
            "id": 3,
            "name": "odd-steps",
            "conclusion": "failure",
            "steps": ["x", {"conclusion": "failure"}, {"conclusion": "success", "name": "ok"}],
        },
        {
            "id": 4,
            "name": "named-step",
            "conclusion": "failure",
            "steps": [{"conclusion": "failure", "name": "pytest"}],
        },
    ]
    _fake_gh(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        answers={_JOBS: _ok(body={"jobs": jobs})},
    )

    found, problem = failed_jobs(repo=tmp_path, run=_RUN)

    assert problem is None
    assert [(job.identifier, job.name, job.failed_step) for job in found] == [
        (2, "no-steps", "unnamed failing step"),
        (3, "odd-steps", "unnamed failing step"),
        (4, "named-step", "pytest"),
    ]


@pytest.mark.parametrize(
    ("answer", "expected_problem"),
    [
        ((1, "", "denied"), "run jobs: denied"),
        (_ok(body=[1]), "run jobs: malformed response"),
        (_ok(body={"jobs": "x"}), "run jobs: malformed response"),
        (
            _ok(body={"jobs": [{"id": "x", "name": "n", "conclusion": "failure"}]}),
            "run jobs: incomplete failed job",
        ),
        (
            _ok(body={"jobs": [{"id": 1, "conclusion": "failure"}]}),
            "run jobs: incomplete failed job",
        ),
    ],
)
def test_failed_jobs_reports_each_unreadable_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answer: tuple[int, str, str],
    expected_problem: str,
) -> None:
    """Scenario 313: an unreadable job list is reported, never read as no failed job."""
    _fake_gh(tmp_path=tmp_path, monkeypatch=monkeypatch, answers={_JOBS: answer})

    assert failed_jobs(repo=tmp_path, run=_RUN) == ((), expected_problem)


def test_failing_tests_are_unique_and_a_log_read_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 313: each failing test is named once; an unreadable log is a problem."""
    log = "FAILED a::t - boom\nFAILED a::t\nERROR b::u\nunrelated\n"
    _fake_gh(tmp_path=tmp_path, monkeypatch=monkeypatch, answers={_LOGS: (0, log, "")})
    assert failing_tests(repo=tmp_path, job=_JOB) == (("a::t", "b::u"), None)

    _fake_gh_failure = {_LOGS: (1, "", "gone")}
    monkeypatch.setenv("FAKE_GH_ANSWERS", json.dumps(_fake_gh_failure))
    assert failing_tests(repo=tmp_path, job=_JOB) == (None, "gone")
