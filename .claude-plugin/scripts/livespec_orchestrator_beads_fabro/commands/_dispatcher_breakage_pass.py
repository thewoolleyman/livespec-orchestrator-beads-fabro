"""Host-side capture of failures from watched scheduled workflows.

The workflow runner cannot reach a repository's Dolt tenant.  This command is
therefore deliberately a *single* host pass: it uses cached ``gh api`` reads,
does not poll, and creates work only through the ordinary capture seam.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from livespec_runtime.work_items.rank import key_between
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    FailedJob,
    Run,
    failed_jobs,
    failing_tests,
    latest_completed_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "breakage_key",
    "run_breakage_pass_command",
]

_BREAKAGE_KEY = "breakage_key"
_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def run_breakage_pass_command(*, args: argparse.Namespace) -> int:
    """Read each watched workflow once and emit its durable pass verdict."""
    repo = Path(args.repo)
    try:
        workflows = _watched_workflows(repo=repo)
    except (TypeError, ValueError) as error:
        _ = write_stdout(text=f"breakage-pass unreadable dispatcher.breakage_workflows: {error}\n")
        return 1

    try:
        config = resolve_store_config(cwd=repo, work_items_arg=None)
    except (OSError, RuntimeError, ValueError) as error:
        _ = write_stdout(text=f"breakage-pass unreadable ledger: {error}\n")
        return 1

    failed = False
    for workflow in workflows:
        verdict, unreadable = _pass_workflow(repo=repo, config=config, workflow=workflow)
        _ = write_stdout(text=verdict + "\n")
        failed = failed or unreadable
    return 1 if failed else 0


def _watched_workflows(*, repo: Path) -> tuple[str, ...]:
    value: object = dispatcher_block(cwd=repo).get("breakage_workflows", [])
    if value == []:
        return ()
    if not isinstance(value, list):
        raise TypeError(  # noqa: TRY003 - this command's public configuration error.
            "must be an array of non-empty workflow file names"
        )
    workflows = cast("list[object]", value)
    if any(not isinstance(item, str) or not item for item in workflows):
        raise ValueError(  # noqa: TRY003 - this command's public configuration error.
            "must be an array of non-empty workflow file names"
        )
    return tuple(cast("str", item) for item in workflows)


def _pass_workflow(  # noqa: C901, PLR0911, PLR0912 - explicit terminal verdicts mirror the contract.
    *, repo: Path, config: StoreConfig, workflow: str
) -> tuple[str, bool]:
    run, problem = latest_completed_run(repo=repo, workflow=workflow)
    if problem is not None:
        return f"breakage-pass {workflow} unreadable {problem}", True
    if run is None:
        return f"breakage-pass {workflow} no-completed-run", False
    if run.conclusion == "success":
        return f"breakage-pass {workflow} run {run.identifier} green", False
    if run.conclusion != "failure":
        return (
            f"breakage-pass {workflow} run {run.identifier} not-concluded {run.conclusion}",
            False,
        )

    jobs, problem = failed_jobs(repo=repo, run=run)
    if problem is not None:
        return f"breakage-pass {workflow} run {run.identifier} unreadable {problem}", True
    try:
        existing = _existing_breakage_items(config=config)
    except (OSError, RuntimeError, ValueError) as error:
        return (
            f"breakage-pass {workflow} run {run.identifier} unreadable ledger dedupe: {error}",
            True,
        )

    filed: list[str] = []
    already_filed: list[str] = []
    for job in jobs:
        key = breakage_key(workflow=workflow, job_name=job.name, head_sha=run.head_sha)
        prior = existing.get(key)
        if prior is not None:
            already_filed.append(prior)
            continue
        item_id, problem = _file_job(
            repo=repo,
            config=config,
            workflow=workflow,
            run=run,
            job=job,
            key=key,
        )
        if problem is not None:
            return f"breakage-pass {workflow} run {run.identifier} unreadable {problem}", True
        if item_id is not None:
            filed.append(item_id)
            existing[key] = item_id

    if filed:
        return f"breakage-pass {workflow} run {run.identifier} filed {', '.join(filed)}", False
    return (
        f"breakage-pass {workflow} run {run.identifier} already-filed {', '.join(already_filed)}",
        False,
    )


def breakage_key(*, workflow: str, job_name: str, head_sha: str) -> str:
    """The stable identity shared by filing and every later dedupe read."""
    return f"{workflow}:{job_name}:{head_sha}"


def _file_job(
    *,
    repo: Path,
    config: StoreConfig,
    workflow: str,
    run: Run,
    job: FailedJob,
    key: str,
) -> tuple[str | None, str | None]:
    tests, log_problem = failing_tests(repo=repo, job=job)
    if log_problem is not None:
        return None, f"job log for {job.name}: {log_problem}"
    description = _description(
        workflow=workflow,
        run=run,
        job=job,
        tests=tests or (),
    )
    openers = minijinja_openers_in_text(source="breakage-pass", text=description)
    if openers:
        return None, "description contains a template opener"
    item = _work_item(config=config, workflow=workflow, job=job, description=description)
    routed = file_captured_work_item(path=config, item=item, checklist=_CHECKLIST)
    if not is_successful(routed):
        return None, f"capture work item for {job.name} was not routed"
    try:
        client = make_beads_client(config=config)
        record = client.show_issue(issue_id=item.id)
        metadata: object = record.get("metadata")
        merged = dict(cast("dict[str, object]", metadata)) if isinstance(metadata, dict) else {}
        merged[_BREAKAGE_KEY] = key
        client.update_issue(
            issue_id=item.id,
            add_labels=[f"breakage:{workflow}"],
            metadata=merged,
        )
    except (OSError, RuntimeError, ValueError) as error:
        return None, f"record breakage key for {job.name}: {error}"
    return item.id, None


def _work_item(*, config: StoreConfig, workflow: str, job: FailedJob, description: str) -> WorkItem:
    return WorkItem(
        id=new_work_item_id(prefix=config.prefix),
        type="bug",
        status="backlog",
        title=f"Fix scheduled workflow {workflow} failing job {job.name}",
        description=description,
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


def _description(*, workflow: str, run: Run, job: FailedJob, tests: tuple[str, ...]) -> str:
    test_lines = "\n".join(f"- Failing test: {test}" for test in tests)
    if not test_lines:
        test_lines = f"- No failing test was named in the log; failing step: {job.failed_step}"
    return (
        "## Definition of Done\n\n"
        "References: ## Dispatcher admission, WIP cap, and post-merge acceptance, "
        "## Scenario 313 — A failed scheduled default-branch workflow run becomes one ledger item"
        " per failed job\n\n"
        f"- The failure in scheduled workflow {workflow}, job {job.name}, is corrected and the job"
        " passes.\n\n"
        f"Run URL: {run.url}\n"
        f"Head commit: {run.head_sha}\n"
        f"Failed job: {job.name}\n"
        f"{test_lines}\n"
    )


def _existing_breakage_items(*, config: StoreConfig) -> dict[str, str]:
    found: dict[str, str] = {}
    for record in make_beads_client(config=config).list_issues():
        metadata: object = record.get("metadata")
        key = (
            cast("dict[str, object]", metadata).get(_BREAKAGE_KEY)
            if isinstance(metadata, dict)
            else None
        )
        identifier: object = record.get("id")
        if isinstance(key, str) and isinstance(identifier, str):
            found[key] = identifier
    return found
