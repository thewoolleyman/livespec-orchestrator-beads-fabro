"""Focused tests for the host-side master-CI dispatch preflight."""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_checks, _dispatcher_step_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_ci_preflight.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight"
_EXIT_PRECONDITION_ERROR = 3
_RED_CONCLUSIONS = (
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
)
_PENDING_STATUSES = ("queued", "in_progress", "waiting", "pending", "requested")
_WAIVER_TOKEN = "dispatcher.step_waivers"
_DEFAULT_BRANCH = "trunk"
_ORIGIN_HEAD = ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
_REPO_VIEW = (
    "gh",
    "repo",
    "view",
    "--json",
    "defaultBranchRef",
    "--jq",
    ".defaultBranchRef.name",
)
# The source-checkout preflight's own git seam. It shares this runner because it
# shares the pre-dispatch gate: it runs FIRST and is fail-closed, so a runner
# answering only `gh` would refuse before the master-CI lookup under test ran.
_IS_WORKTREE = ("git", "rev-parse", "--is-inside-work-tree")
_ORIGIN_REFS = ("git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
_SOURCE_HEAD = ("git", "rev-parse", "HEAD")
_HEAD_ANCESTOR = ("git", "merge-base", "--is-ancestor", "abc1234", f"origin/{_DEFAULT_BRANCH}")


class _MasterCiRefusal(Protocol):
    detail: str
    record: dict[str, object]


class _MasterCiOutcome(Protocol):
    refusal: _MasterCiRefusal | None
    record: dict[str, object]


class _PreflightModule(Protocol):
    def master_ci_preflight(self, *, repo: Path, runner: _Runner) -> _MasterCiOutcome:
        """Return the master-CI preflight outcome."""


@dataclass(kw_only=True)
class _Runner:
    """Argv-keyed command stand-in; an unscripted argv answers a plain failure."""

    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

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
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unscripted"))


def _module() -> _PreflightModule:
    assert _MODULE_PATH.is_file()
    return cast("_PreflightModule", importlib.import_module(_MODULE_NAME))


def _result(*, exit_code: int = 0, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _run_list_payload(
    *, status: str = "completed", conclusion: str | None = "success", database_id: int = 303
) -> str:
    return json.dumps([{"status": status, "conclusion": conclusion, "databaseId": database_id}])


def _jobs_payload(
    *,
    job_conclusion: str | None = "success",
    job_status: str = "completed",
    job_name: str = "ci-green",
) -> str:
    jobs: list[dict[str, str | None]] = [{"name": "export-telemetry", "conclusion": "failure"}]
    if job_conclusion is not None:
        jobs.append({"name": job_name, "conclusion": job_conclusion, "status": job_status})
    return json.dumps({"jobs": jobs})


def _run_list_argv(*, branch: str = _DEFAULT_BRANCH, workflow: str = "CI") -> tuple[str, ...]:
    return (
        "gh",
        "run",
        "list",
        "--branch",
        branch,
        "--limit",
        "1",
        "--workflow",
        workflow,
        "--json",
        "status,conclusion,databaseId",
    )


def _results(
    *,
    run_list: CommandResult | None = None,
    jobs: CommandResult | None = None,
    auth: CommandResult | None = None,
    origin_head: CommandResult | None = None,
    repo_view: CommandResult | None = None,
    view_run_id: str = "303",
    workflow: str = "CI",
) -> dict[tuple[str, ...], CommandResult]:
    return {
        _IS_WORKTREE: _result(stdout="true\n"),
        _ORIGIN_REFS: _result(stdout=f"origin/{_DEFAULT_BRANCH}\n"),
        _SOURCE_HEAD: _result(stdout="abc1234\n"),
        _HEAD_ANCESTOR: _result(),
        _ORIGIN_HEAD: (
            origin_head
            if origin_head is not None
            else _result(stdout=f"origin/{_DEFAULT_BRANCH}\n")
        ),
        _REPO_VIEW: repo_view if repo_view is not None else _result(stdout="fallback-branch\n"),
        ("gh", "auth", "token"): auth if auth is not None else _result(stdout="secret\n"),
        _run_list_argv(workflow=workflow): (
            run_list if run_list is not None else _result(stdout=_run_list_payload())
        ),
        ("gh", "run", "view", view_run_id, "--json", "jobs"): (
            jobs if jobs is not None else _result(stdout=_jobs_payload())
        ),
    }


def _outcome(*, repo: Path, runner: _Runner) -> _MasterCiOutcome:
    return _module().master_ci_preflight(repo=repo, runner=runner)


def _declare(*, repo: Path, workflow: str, job: str) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"master_ci": {"workflow": workflow, "job": job}}
                }
            }
        ),
        encoding="utf-8",
    )


def test_a_green_aggregate_job_passes_and_journals_the_pass(tmp_path: Path) -> None:
    runner = _Runner(results=_results())

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["status"] == "passed"
    assert outcome.record["step"] == "master-ci"
    assert outcome.record["branch"] == _DEFAULT_BRANCH
    assert outcome.record["aggregate_job"] == "ci-green"
    assert outcome.record["pipeline_resolution"] == "default"
    assert outcome.record["declaring_key"] == "dispatcher.master_ci"


def test_the_run_lookup_targets_the_resolved_default_branch(tmp_path: Path) -> None:
    """The branch comes from `origin/HEAD`, never from a shipped literal."""
    runner = _Runner(results=_results())

    assert _outcome(repo=tmp_path, runner=runner).refusal is None
    assert _run_list_argv() in runner.calls
    assert not any(call[:5] == ("gh", "run", "list", "--branch", "master") for call in runner.calls)


def test_the_preflight_source_carries_no_branch_literal() -> None:
    """The discriminating token: a quoted bare branch name anywhere in the module.

    A count of the word would be worthless — the ratified STEP identifier is
    `master-ci` and the documented escape hatch is named
    `master-health-restoration`, so both legitimately survive. What must not
    survive is the branch name as a standalone string constant.
    """
    source = _MODULE_PATH.read_text(encoding="utf-8")

    assert '"master"' not in source
    assert "'master'" not in source


def test_an_unresolvable_origin_head_falls_back_to_the_forge(tmp_path: Path) -> None:
    empty = _Runner(
        results={
            **_results(origin_head=_result(stdout="\n")),
            _run_list_argv(branch="fallback-branch"): _result(stdout=_run_list_payload()),
        }
    )
    failed = _Runner(
        results={
            **_results(origin_head=_result(exit_code=128, stderr="no origin/HEAD")),
            _run_list_argv(branch="fallback-branch"): _result(stdout=_run_list_payload()),
        }
    )

    for runner in (empty, failed):
        assert _outcome(repo=tmp_path, runner=runner).refusal is None
        assert _run_list_argv(branch="fallback-branch") in runner.calls


def test_a_wholly_unresolvable_branch_refuses_with_the_waiver_escape(tmp_path: Path) -> None:
    blank = _Runner(
        results=_results(origin_head=_result(stdout="\n"), repo_view=_result(stdout="\n"))
    )
    failed = _Runner(
        results=_results(
            origin_head=_result(exit_code=128), repo_view=_result(exit_code=1, stderr="no auth")
        )
    )

    for runner in (blank, failed):
        refusal = _outcome(repo=tmp_path, runner=runner).refusal
        assert refusal is not None
        assert "default branch could not be resolved" in refusal.detail
        assert _WAIVER_TOKEN in refusal.detail


def test_a_declared_pipeline_is_looked_up_and_passes(tmp_path: Path) -> None:
    _declare(repo=tmp_path, workflow="build.yml", job="all-green")
    runner = _Runner(
        results=_results(
            workflow="build.yml",
            jobs=_result(stdout=_jobs_payload(job_name="all-green")),
        )
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["workflow"] == "build.yml"
    assert outcome.record["aggregate_job"] == "all-green"
    assert outcome.record["pipeline_resolution"] == "declared"
    assert _run_list_argv(workflow="build.yml") in runner.calls


def test_a_declared_pipeline_that_is_red_refuses_naming_the_run(tmp_path: Path) -> None:
    _declare(repo=tmp_path, workflow="build.yml", job="all-green")
    runner = _Runner(
        results=_results(
            workflow="build.yml",
            run_list=_result(stdout=_run_list_payload(database_id=30316766663)),
            jobs=_result(stdout=_jobs_payload(job_name="all-green", job_conclusion="failure")),
            view_run_id="30316766663",
        )
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["reason"] == "master-ci-red"
    assert outcome.record["run_database_id"] == "30316766663"
    assert "30316766663" in outcome.refusal.detail
    assert "all-green" in outcome.refusal.detail


@pytest.mark.parametrize("conclusion", _RED_CONCLUSIONS)
def test_every_red_conclusion_refuses(tmp_path: Path, conclusion: str) -> None:
    runner = _Runner(
        results=_results(jobs=_result(stdout=_jobs_payload(job_conclusion=conclusion)))
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert outcome.record["reason"] == "master-ci-red"


def test_a_red_run_rollup_with_a_green_aggregate_job_still_passes(tmp_path: Path) -> None:
    """The AGGREGATE JOB is the required check, not the run's own rollup."""
    runner = _Runner(
        results=_results(run_list=_result(stdout=_run_list_payload(conclusion="failure")))
    )

    assert _outcome(repo=tmp_path, runner=runner).refusal is None


def test_a_host_with_no_usable_credential_refuses_with_the_waiver_escape(tmp_path: Path) -> None:
    absent = _Runner(
        results=_results(
            auth=_result(exit_code=127, stderr="gh: command not found\n"),
            run_list=_result(exit_code=127, stderr="gh: command not found\n"),
        )
    )
    unauthenticated = _Runner(
        results=_results(
            auth=_result(exit_code=1, stderr="not logged in\n"),
            run_list=_result(exit_code=1, stderr="HTTP 401\n"),
        )
    )

    for runner in (absent, unauthenticated):
        outcome = _outcome(repo=tmp_path, runner=runner)
        assert outcome.refusal is not None
        assert outcome.record["reason"] == "master-ci-unprovable"
        assert "no usable `gh` credential" in outcome.refusal.detail
        assert "gh auth login" in outcome.refusal.detail
        assert _WAIVER_TOKEN in outcome.refusal.detail


def test_an_unresolvable_pipeline_names_the_resolution_the_key_and_the_escape(
    tmp_path: Path,
) -> None:
    _declare(repo=tmp_path, workflow="build.yml", job="all-green")
    runner = _Runner(
        results=_results(
            workflow="build.yml",
            run_list=_result(exit_code=1, stderr="could not find any workflows named build.yml\n"),
        )
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    detail = outcome.refusal.detail
    assert "Resolution attempted: declared" in detail
    assert "dispatcher.master_ci" in detail
    assert _WAIVER_TOKEN in detail


@pytest.mark.parametrize(
    "declaration",
    [
        "CI",
        {"job": "all-green"},
        {"workflow": "build.yml"},
        {"workflow": "", "job": "all-green"},
    ],
)
def test_a_present_but_unusable_declaration_refuses_before_any_lookup(
    tmp_path: Path, declaration: object
) -> None:
    """A typo'd declaration must not slide onto the convention and prove IT green.

    The load-bearing assertion is `runner.calls == []`: the runner here is
    scripted to answer a fully GREEN default-convention pipeline, so under the
    retired fallback every case below would pass the preflight on evidence from
    a workflow the repository has said is not its own. An empty call list proves
    no lookup was attempted at all, which no green answer can fake.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"master_ci": declaration}}}
        ),
        encoding="utf-8",
    )
    runner = _Runner(results=_results())

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert runner.calls == []
    assert outcome.record["reason"] == "master-ci-unprovable"
    assert outcome.record["workflow"] == "<unresolved>"
    assert outcome.record["aggregate_job"] == "<unresolved>"
    assert outcome.record["pipeline_resolution"] == "declared"
    detail = outcome.refusal.detail
    assert "unusable" in detail
    assert "dispatcher.master_ci" in detail
    assert _WAIVER_TOKEN in detail


def test_an_undeclared_unresolvable_pipeline_names_the_default_resolution(tmp_path: Path) -> None:
    runner = _Runner(
        results=_results(run_list=_result(exit_code=1, stderr="no workflow named CI\n"))
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert "Resolution attempted: default convention" in outcome.refusal.detail
    assert "dispatcher.master_ci" in outcome.refusal.detail
    assert _WAIVER_TOKEN in outcome.refusal.detail


def test_a_repository_with_no_runs_yet_refuses_with_the_waiver_escape(tmp_path: Path) -> None:
    runner = _Runner(results=_results(run_list=_result(stdout="[]")))

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert "no runs yet" in outcome.refusal.detail
    assert _WAIVER_TOKEN in outcome.refusal.detail
    assert outcome.record["run_database_id"] == "<none>"


@pytest.mark.parametrize("status", _PENDING_STATUSES)
def test_a_still_pending_latest_run_refuses_naming_the_retry(tmp_path: Path, status: str) -> None:
    runner = _Runner(results=_results(run_list=_result(stdout=_run_list_payload(status=status))))

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert f"is still {status}" in outcome.refusal.detail
    assert "retry the dispatch when the run concludes" in outcome.refusal.detail


def test_a_still_pending_aggregate_job_refuses_naming_the_retry(tmp_path: Path) -> None:
    runner = _Runner(results=_results(jobs=_result(stdout=_jobs_payload(job_status="in_progress"))))

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert "retry the dispatch when the run concludes" in outcome.refusal.detail


def test_an_unrecognized_aggregate_conclusion_refuses(tmp_path: Path) -> None:
    runner = _Runner(results=_results(jobs=_result(stdout=_jobs_payload(job_conclusion="neutral"))))

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert "neither green nor red" in outcome.refusal.detail


def test_a_missing_aggregate_job_refuses_naming_the_resolved_job(tmp_path: Path) -> None:
    runner = _Runner(results=_results(jobs=_result(stdout=_jobs_payload(job_conclusion=None))))

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    assert "aggregate job `ci-green` is missing" in outcome.refusal.detail


def test_a_failed_aggregate_job_lookup_refuses(tmp_path: Path) -> None:
    named = _Runner(results=_results(jobs=_result(exit_code=1, stderr="view failed\n")))
    silent = _Runner(results=_results(jobs=_result(exit_code=1)))

    for runner in (named, silent):
        assert _outcome(repo=tmp_path, runner=runner).refusal is not None


def test_malformed_payloads_refuse_as_unprovable(tmp_path: Path) -> None:
    malformed_list = _Runner(results=_results(run_list=_result(stdout=json.dumps({"a": 1}))))
    malformed_record = _Runner(results=_results(run_list=_result(stdout=json.dumps(["bad"]))))
    malformed_view = _Runner(results=_results(jobs=_result(stdout=json.dumps([]))))
    malformed_jobs = _Runner(results=_results(jobs=_result(stdout=json.dumps({"jobs": {}}))))

    for runner in (malformed_list, malformed_record, malformed_view, malformed_jobs):
        assert _outcome(repo=tmp_path, runner=runner).refusal is not None


def test_a_run_without_a_database_id_is_named_as_unknown(tmp_path: Path) -> None:
    runner = _Runner(
        results={
            **_results(
                run_list=_result(
                    stdout=json.dumps([{"status": "completed", "conclusion": "success"}])
                )
            ),
            ("gh", "run", "view", "<none>", "--json", "jobs"): _result(stdout=_jobs_payload()),
        }
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is None
    assert outcome.record["run_database_id"] == "<none>"


def test_non_dict_jobs_are_ignored_while_finding_the_aggregate_job(tmp_path: Path) -> None:
    runner = _Runner(
        results=_results(
            jobs=_result(
                stdout=json.dumps({"jobs": ["bad", {"name": "ci-green", "conclusion": "success"}]})
            )
        )
    )

    assert _outcome(repo=tmp_path, runner=runner).refusal is None


def test_refusal_text_names_the_documented_master_health_recovery(tmp_path: Path) -> None:
    runner = _Runner(
        results=_results(
            run_list=_result(stdout=_run_list_payload(database_id=30316766663)),
            jobs=_result(stdout=_jobs_payload(job_conclusion="failure")),
            view_run_id="30316766663",
        )
    )

    outcome = _outcome(repo=tmp_path, runner=runner)

    assert outcome.refusal is not None
    detail = outcome.refusal.detail
    assert "30316766663" in detail
    assert "master-health-restoration" in detail
    assert "in-session" in detail
    assert "PR CI is independent of the default branch" in detail
    assert "repeat-flakes" in detail
    assert "AGENTS.md" in detail
    assert "gh run rerun 30316766663 --failed" not in detail
    assert outcome.record["recovery"] == [
        "For a master-health-restoration item parked behind a red default branch, drive it "
        "in-session through worktree -> PR -> merge; PR CI is independent of the default branch.",
        "See AGENTS.md and .claude-plugin/prose/implement.md Step 0 for the documented "
        "escape hatch and the repeat-flake caveat.",
    ]


def test_lever_env_cannot_make_a_red_default_branch_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_SKIP_MASTER_CI_PREFLIGHT", "1")
    monkeypatch.setenv("CHECK_MASTER_CI_GREEN_SEVERITY", "warning")
    runner = _Runner(results=_results(jobs=_result(stdout=_jobs_payload(job_conclusion="failure"))))

    assert _outcome(repo=tmp_path, runner=runner).refusal is not None


def test_dispatch_preamble_refuses_before_receiver_or_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _MODULE_PATH.is_file()
    journal = tmp_path / "journal.jsonl"
    args = argparse.Namespace(fabro_bin=str(tmp_path / "fabro"), janitor=None, journal=str(journal))
    runner = _Runner(results=_results(jobs=_result(stdout=_jobs_payload(job_conclusion="failure"))))
    _ = (tmp_path / "fabro").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "fabro").chmod(0o755)
    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: runner)

    assert _dispatcher_run_checks.dispatch_preamble(args=args, repo=tmp_path) == (
        None,
        _EXIT_PRECONDITION_ERROR,
    )
    records = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    # Both pre-dispatch steps journal, in gate order: the source checkout passes
    # and says so, then the master-CI step refuses.
    assert [record["step"] for record in records] == ["source-checkout", "master-ci"]
    assert records[-1]["stage"] == "master-ci-preflight"


def test_existing_in_sandbox_master_ci_gate_and_janitor_aggregate_are_unchanged() -> None:
    master_ci_gate = Path(
        ".venv/lib/python3.10/site-packages/livespec_dev_tooling/checks/master_ci_green.py"
    ).read_text(encoding="utf-8")
    justfile = Path("justfile").read_text(encoding="utf-8")

    assert '"failure", "cancelled", "timed_out", "action_required", "stale"' in master_ci_gate
    assert "startup_failure" in master_ci_gate
    assert "check-master-ci-green" in justfile
