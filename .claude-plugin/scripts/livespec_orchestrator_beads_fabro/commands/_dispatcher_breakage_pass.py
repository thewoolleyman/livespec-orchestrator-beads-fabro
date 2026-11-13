"""Host-side filing of failed scheduled workflow jobs through intake."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    ScheduledRun as _Run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    failed_jobs,
    job_evidence,
    latest_completed_run,
    workflow_api,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_intake import (
    build_breakage_item,
    known_breakage_keys,
    template_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "BreakagePassOutcome",
    "add_breakage_pass_arguments",
    "breakage_pass",
    "run_breakage_pass_command",
]

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
        known = known_breakage_keys(records=client.list_issues())
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
    if not isinstance(value, list):
        return "dispatcher.breakage_workflows must be an array of non-empty strings"
    workflows = cast("list[object]", value)
    if any(not isinstance(item, str) or not item for item in workflows):
        return "dispatcher.breakage_workflows must be an array of non-empty strings"
    return tuple(cast("str", item) for item in workflows)


def _workflow_pass(*, pass_: _Pass) -> tuple[str, bool]:
    run = latest_completed_run(
        result=workflow_api(
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
    return (
        (f"{prefix} green", False)
        if run.conclusion == "success"
        else (
            f"{prefix} not-concluded {run.conclusion}",
            False,
        )
    )


def _file_failed_jobs(*, pass_: _Pass, run: _Run) -> tuple[str, bool]:
    prefix = f"{pass_.workflow} run {run.identifier}:"
    jobs = failed_jobs(
        result=workflow_api(
            repo=pass_.repo,
            runner=pass_.runner,
            endpoint=f"repos/{{owner}}/{{repo}}/actions/runs/{run.identifier}/jobs?per_page=100",
        )
    )
    if isinstance(jobs, str):
        return f"{prefix} unreadable {jobs}", True
    evidence = job_evidence(repo=pass_.repo, runner=pass_.runner, jobs=jobs)
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
        item = build_breakage_item(
            item_id=item_id,
            workflow=pass_.workflow,
            job=job,
            run=run,
            tests=tests,
            captured_at=utc_now_iso(),
        )
        refusal = template_refusal(description=item.description)
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
