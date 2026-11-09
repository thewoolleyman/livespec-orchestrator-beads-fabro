"""The `correct-unmerged-attempt` action: correct a repair whose expedited PR closed unmerged.

`SPECIFICATION/contracts.md` section "Carrier identity before and after PR
creation". It trusts no caller-typed result: the chain names the bound PR, and
`gh pr view` reports its state, head branch and head commit; the operator names
only the failed run, and `gh run view` reports its head, status and conclusion.
The planner refuses by name unless the PR is closed and not merged at the
carrier's exact head and ref, and the run completed with conclusion failure on
that head. Nothing is read from the forge for an attempt that is not the
current `pr-bound` repair.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_unmerged_correction import (
    NOT_ELIGIBLE,
    UnmergedFailure,
    unmerged_eligible,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_completion import (
    observe_master_run,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_decode import decode_record
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    Correction,
    RecoveryEntry,
    enter_unmerged_correction,
)

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "PR_UNOBSERVABLE",
    "RUN_UNOBSERVABLE",
    "UnmergedRequest",
    "correct_unmerged_action",
    "correct_unmerged_from_forge",
]

PR_UNOBSERVABLE = "incident-correction-pr-unobservable"
RUN_UNOBSERVABLE = "incident-correction-run-unobservable"
_PR_FIELDS = "number,state,headRefName,headRefOid"
_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class UnmergedRequest:
    """What the operator names: the failed run, the correction and its fresh target ref."""

    run_id: str
    correction: Correction
    target_ref: str


def _observe_pr(
    *, runner: CommandRunner, repo: Path, repository: str, pr_number: int
) -> dict[str, object] | AuthorityRefusal:
    result = runner.run(
        argv=["gh", "pr", "view", str(pr_number), "--repo", repository, "--json", _PR_FIELDS],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    number = value.get("number")
    texts = [value.get(key) for key in ("state", "headRefName", "headRefOid")]
    if type(number) is not int or not all(isinstance(text, str) for text in texts):
        reason = result.stderr.strip() or "no number, state, headRefName and headRefOid"
        return AuthorityRefusal(code=PR_UNOBSERVABLE, detail=f"PR #{pr_number}: {reason}")
    return value


def correct_unmerged_from_forge(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    request: UnmergedRequest,
) -> RecoveryEntry | AuthorityRefusal:
    """Read the bound PR and the named run from the forge, then open the corrected attempt."""
    attempt = reading.attempt
    if not unmerged_eligible(reading=reading):
        return AuthorityRefusal(
            code=NOT_ELIGIBLE,
            detail=f"{attempt.item_id}: {attempt.phase} is no current PR-bound repair",
        )
    pr = _observe_pr(runner=runner, repo=repo, repository=repository, pr_number=attempt.pr_number)
    if isinstance(pr, AuthorityRefusal):
        return pr
    run = observe_master_run(runner=runner, repo=repo, repository=repository, run_id=request.run_id)
    if isinstance(run, AuthorityRefusal):
        return AuthorityRefusal(code=RUN_UNOBSERVABLE, detail=run.detail)
    observed = UnmergedFailure(
        pr_number=cast("int", pr["number"]),
        pr_state=cast("str", pr["state"]),
        head_ref=cast("str", pr["headRefName"]),
        pr_head=cast("str", pr["headRefOid"]),
        run_id=run.run_id,
        run_head=run.head,
        run_conclusion=run.conclusion,
        run_complete=run.complete,
    )
    return enter_unmerged_correction(
        client=client,
        reading=reading,
        observed=observed,
        correction=request.correction,
        target_ref=request.target_ref,
    )


def correct_unmerged_action(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> RecoveryEntry | AuthorityRefusal:
    """The lifecycle handler: decode the correction, then correct from the forge's facts."""
    correction = decode_record(
        text=args.correction_json, shape=Correction, flag="--correction-json"
    )
    if isinstance(correction, AuthorityRefusal):
        return correction
    request = UnmergedRequest(
        run_id=args.failed_run, correction=correction, target_ref=args.target_ref
    )
    return correct_unmerged_from_forge(
        client=client,
        reading=reading,
        runner=runner,
        repo=args.repo,
        repository=args.repository,
        request=request,
    )
