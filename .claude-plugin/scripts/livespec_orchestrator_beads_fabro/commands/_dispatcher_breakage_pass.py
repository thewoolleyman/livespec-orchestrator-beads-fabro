"""Host-side filing of failed scheduled workflow jobs through intake."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_runtime.work_items.rank import key_between
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "BreakagePassOutcome",
    "add_breakage_pass_arguments",
    "breakage_pass",
    "run_breakage_pass_command",
]

_CACHE_DURATION = "30m"
_GH_TIMEOUT_SECONDS = 30.0
_FAILURE_LINE = re.compile(r"[\w./-]+::[\w\[\]-]+")
_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


@dataclass(frozen=True, kw_only=True)
class BreakagePassOutcome:
    """The journal-ready verdict lines and process status of one pass."""

    exit_code: int
    lines: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _FailedJob:
    identifier: str
    name: str
    failing_step: str


@dataclass(frozen=True, kw_only=True)
class _Run:
    identifier: str
    conclusion: str
    head_sha: str
    url: str


@dataclass(frozen=True, kw_only=True)
class _Pass:
    repo: Path
    runner: CommandRunner
    workflow: str
    branch: str
    config: StoreConfig
    client: BeadsClient
    known: dict[str, str]


def add_breakage_pass_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the intentionally small host-only breakage-pass interface."""
    _ = parser.add_argument("--repo", required=True)


def run_breakage_pass_command(*, args: argparse.Namespace) -> int:
    """Run one pass and leave its per-workflow verdicts on the timer journal."""
    outcome = breakage_pass(repo=Path(args.repo), runner=ShellCommandRunner())
    for line in outcome.lines:
        write_stdout(text=f"{line}\n")
    return outcome.exit_code


def breakage_pass(*, repo: Path, runner: CommandRunner) -> BreakagePassOutcome:
    """Read each watched workflow once and file its unseen failed jobs."""
    workflows = _workflows(repo=repo)
    if isinstance(workflows, str):
        return BreakagePassOutcome(exit_code=1, lines=(f"unreadable {workflows}",))
    if not workflows:
        return BreakagePassOutcome(exit_code=0, lines=())
    branch = resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        return BreakagePassOutcome(
            exit_code=1,
            lines=tuple(f"{workflow}: unreadable default branch" for workflow in workflows),
        )
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    client = make_beads_client(config=config)
    try:
        known = _known_keys(records=client.list_issues())
    except BeadsCommandError as error:
        return BreakagePassOutcome(
            exit_code=1,
            lines=tuple(f"{workflow}: unreadable ledger: {error}" for workflow in workflows),
        )
    verdicts = tuple(
        _workflow_pass(
            pass_=_Pass(
                repo=repo,
                runner=runner,
                workflow=workflow,
                branch=branch,
                config=config,
                client=client,
                known=known,
            )
        )
        for workflow in workflows
    )
    return BreakagePassOutcome(
        exit_code=1 if any(failed for _, failed in verdicts) else 0,
        lines=tuple(verdict for verdict, _ in verdicts),
    )


def _workflows(*, repo: Path) -> tuple[str, ...] | str:
    value = dispatcher_block(cwd=repo).get("breakage_workflows", [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        return "dispatcher.breakage_workflows must be an array of non-empty strings"
    return tuple(cast("list[str]", value))


def _workflow_pass(*, pass_: _Pass) -> tuple[str, bool]:
    run = _latest_run(
        result=_api(
            repo=pass_.repo,
            runner=pass_.runner,
            endpoint=(
                f"repos/{{owner}}/{{repo}}/actions/workflows/{pass_.workflow}/runs?"
                f"branch={pass_.branch}&status=completed&per_page=1"
            ),
        )
    )
    if not isinstance(run, _Run):
        return _run_reading_verdict(workflow=pass_.workflow, run=run)
    if run.conclusion != "failure":
        return _conclusion_verdict(workflow=pass_.workflow, run=run)
    return _file_failed_jobs(pass_=pass_, run=run)


def _run_reading_verdict(*, workflow: str, run: str | None) -> tuple[str, bool]:
    if isinstance(run, str):
        return f"{workflow}: unreadable {run}", True
    return f"{workflow}: no-completed-run", False


def _conclusion_verdict(*, workflow: str, run: _Run) -> tuple[str, bool]:
    prefix = f"{workflow} run {run.identifier}:"
    return (f"{prefix} green", False) if run.conclusion == "success" else (
        f"{prefix} not-concluded {run.conclusion}",
        False,
    )


def _file_failed_jobs(*, pass_: _Pass, run: _Run) -> tuple[str, bool]:
    prefix = f"{pass_.workflow} run {run.identifier}:"
    jobs = _failed_jobs(
        result=_api(
            repo=pass_.repo,
            runner=pass_.runner,
            endpoint=f"repos/{{owner}}/{{repo}}/actions/runs/{run.identifier}/jobs?per_page=100",
        )
    )
    if isinstance(jobs, str):
        return f"{prefix} unreadable {jobs}", True
    evidence = _job_evidence(repo=pass_.repo, runner=pass_.runner, jobs=jobs)
    if isinstance(evidence, str):
        return f"{prefix} unreadable {evidence}", True
    item_ids: list[str] = []
    filed = False
    for job, tests in zip(jobs, evidence, strict=True):
        key = f"{pass_.workflow}:{job.name}:{run.head_sha}"
        if key in pass_.known:
            item_ids.append(pass_.known[key])
            continue
        item_id = new_work_item_id(prefix=pass_.config.prefix)
        item = _item(
            item_id=item_id,
            workflow=pass_.workflow,
            job=job,
            run=run,
            tests=tests,
        )
        refusal = _template_refusal(description=item.description)
        if refusal is not None:
            return f"{prefix} unreadable {refusal}", True
        routed = file_captured_work_item(path=pass_.config, item=item, checklist=_CHECKLIST)
        if not is_successful(routed):
            return f"{prefix} unreadable intake could not route {key}", True
        pass_.client.update_issue(
            issue_id=item_id,
            add_labels=[f"breakage:{pass_.workflow}"],
            metadata={"breakage_key": key},
        )
        pass_.known[key] = item_id
        item_ids.append(item_id)
        filed = True
    verb = "filed" if filed else "already-filed"
    return f"{prefix} {verb} {', '.join(item_ids)}", False


def _api(*, repo: Path, runner: CommandRunner, endpoint: str) -> CommandResult:
    return runner.run(
        argv=["gh", "api", "--cache", _CACHE_DURATION, endpoint],
        cwd=repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )


def _latest_run(*, result: CommandResult) -> _Run | str | None:
    payload = _json_object(result=result)
    runs = None if payload is None else payload.get("workflow_runs")
    if not isinstance(runs, list):
        return "workflow runs"
    if not runs:
        return None
    entry = runs[0] if isinstance(runs[0], dict) else {}
    fields = (
        entry.get("id"),
        entry.get("conclusion"),
        entry.get("head_sha"),
        entry.get("html_url"),
    )
    if not all(isinstance(field, str | int) and str(field) for field in fields):
        return "workflow run fields"
    return _Run(
        identifier=str(fields[0]),
        conclusion=str(fields[1]),
        head_sha=str(fields[2]),
        url=str(fields[3]),
    )


def _failed_jobs(*, result: CommandResult) -> tuple[_FailedJob, ...] | str:
    payload = _json_object(result=result)
    jobs = None if payload is None else payload.get("jobs")
    if not isinstance(jobs, list):
        return "workflow jobs"
    found: list[_FailedJob] = []
    for raw in jobs:
        if not isinstance(raw, dict) or raw.get("conclusion") != "failure":
            continue
        identifier, name = raw.get("id"), raw.get("name")
        if not isinstance(identifier, str | int) or not isinstance(name, str) or not name:
            return "workflow job fields"
        found.append(
            _FailedJob(identifier=str(identifier), name=name, failing_step=_failed_step(job=raw))
        )
    return tuple(found)


def _job_evidence(
    *, repo: Path, runner: CommandRunner, jobs: tuple[_FailedJob, ...]
) -> tuple[tuple[str, ...], ...] | str:
    tests: list[tuple[str, ...]] = []
    for job in jobs:
        result = _api(
            repo=repo,
            runner=runner,
            endpoint=f"repos/{{owner}}/{{repo}}/actions/jobs/{job.identifier}/logs",
        )
        if result.exit_code != 0:
            return "workflow job log"
        tests.append(_tests_in_log(text=result.stdout))
    return tuple(tests)


def _tests_in_log(*, text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group(0)
            for line in text.splitlines()
            if "FAILED" in line
            for match in _FAILURE_LINE.finditer(line)
        )
    )


def _failed_step(*, job: dict[object, object]) -> str:
    steps = job.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get("conclusion") == "failure":
                name = step.get("name")
                if isinstance(name, str) and name:
                    return name
    return "<unnamed failing step>"


def _known_keys(*, records: list[dict[str, object]]) -> dict[str, str]:
    return {
        key: identifier
        for record in records
        if isinstance(record.get("metadata"), dict)
        and isinstance(key := record["metadata"].get("breakage_key"), str)
        and isinstance(identifier := record.get("id"), str)
    }


def _item(
    *, item_id: str, workflow: str, job: _FailedJob, run: _Run, tests: tuple[str, ...]
) -> WorkItem:
    evidence = "\n".join(f"- {test}" for test in tests) if tests else (
        f"No failing test named; failing step: {job.failing_step}"
    )
    return WorkItem(
        id=item_id,
        type="bug",
        status="backlog",
        title=f"CI breakage: {workflow} — {job.name}",
        description=(
            f"Scheduled workflow failure for `{workflow}` job `{job.name}`.\n\n"
            f"Run URL: {run.url}\nHead commit: {run.head_sha}\n{evidence}\n\n"
            "## Definition of Done\n\n"
            "References: ## Scheduled-workflow breakage pass\n\n"
            f"- The failing `{workflow}` job `{job.name}` is investigated and its failure is "
            "resolved.\n"
        ),
        origin="freeform",
        gap_id=None,
        rank=key_between(a=None, b=None),
        assignee=None,
        depends_on=(),
        captured_at=utc_now_iso(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _template_refusal(*, description: str) -> str | None:
    findings = minijinja_openers_in_text(source="breakage-pass", text=description)
    if not findings:
        return None
    return f"template opener present: {', '.join(finding.opener for finding in findings)}"


def _json_object(*, result: CommandResult) -> dict[str, object] | None:
    if result.exit_code != 0:
        return None
    try:
        payload: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", payload) if isinstance(payload, dict) else None
