"""Close a forge-proven scratch-branch drill without treating it as repayment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_phases import lifecycle_state_for
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_history
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)

if TYPE_CHECKING:
    from pathlib import Path
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["DrillClose", "close_drill"]
DRILL_CLOSED = "drill-closed"
NOT_A_DRILL = "incident-not-a-recorded-drill"
EVIDENCE_UNAVAILABLE = "incident-drill-evidence-unavailable"
_ALLOWED = frozenset(
    ("repair", "master-observation", "reverting", "rollback-conflict", "collecting-failures")
)
_SCRATCH = "incident-scratch/"


@dataclass(frozen=True, kw_only=True)
class DrillClose:
    reading: IncidentReading
    lifecycle_state: str
    repayment_outstanding: bool


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _carriers(
    *, history: tuple[IncidentAttempt, ...]
) -> tuple[IncidentAttempt, ...] | AuthorityRefusal:
    latest: dict[str, IncidentAttempt] = {}
    for attempt in history:
        if not isinstance(attempt.carrier, PrBound) or attempt.pr_number <= 0:
            return _refuse(
                code=NOT_A_DRILL, detail=f"carrier on {attempt.attempt_id} is not pr-bound"
            )
        latest[attempt.carrier.target_ref] = attempt
    return tuple(latest.values())


def _evidence(
    *, history: tuple[IncidentAttempt, ...], runner: CommandRunner, repo: Path, repository: str
) -> AuthorityRefusal | None:
    carriers = _carriers(history=history)
    if isinstance(carriers, AuthorityRefusal):
        return carriers
    for attempt in carriers:
        result = runner.run(
            argv=[
                "gh",
                "pr",
                "view",
                str(attempt.pr_number),
                "--repo",
                repository,
                "--json",
                "number,state,baseRefName",
            ],
            cwd=repo,
            timeout_seconds=60.0,
        )
        value = parse_json(text=result.stdout) if result.exit_code == 0 else None
        if not isinstance(value, dict):
            return _refuse(
                code=EVIDENCE_UNAVAILABLE, detail=f"PR #{attempt.pr_number}: forge read failed"
            )
        pull = cast("dict[str, object]", value)
        if (
            pull.get("number") != attempt.pr_number
            or not isinstance(pull.get("state"), str)
            or not isinstance(pull.get("baseRefName"), str)
        ):
            return _refuse(
                code=EVIDENCE_UNAVAILABLE, detail=f"PR #{attempt.pr_number}: forge read incomplete"
            )
        if pull["state"] != "MERGED" or not cast("str", pull["baseRefName"]).startswith(_SCRATCH):
            return _refuse(code=NOT_A_DRILL, detail=f"carrier {attempt.carrier.target_ref}")
    for attempt in history:
        for commit in attempt.landed_commits:
            result = runner.run(
                argv=[
                    "gh",
                    "api",
                    f"repos/{repository}/compare/{commit}...master",
                    "--jq",
                    ".ahead_by",
                ],
                cwd=repo,
                timeout_seconds=60.0,
            )
            if result.exit_code != 0 or result.stdout.strip() not in {"0", "1"}:
                return _refuse(code=EVIDENCE_UNAVAILABLE, detail=f"commit {commit}: unreadable")
            if result.stdout.strip() == "0":
                return _refuse(code=NOT_A_DRILL, detail=f"landed commit {commit}")
    return None


def close_drill(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> DrillClose | AuthorityRefusal:
    """Write `drill-closed` only after fresh forge evidence proves the recorded drill."""
    if not reading.is_current:
        return _refuse(code="incident-generation-stale", detail=reading.attempt.item_id)
    if reading.attempt.phase not in _ALLOWED:
        return _refuse(code=NOT_A_DRILL, detail=f"phase {reading.attempt.phase}")
    history = read_history(client=client, repository=repository, item_id=reading.attempt.item_id)
    if isinstance(history, AuthorityRefusal):
        return history
    refusal = _evidence(history=history, runner=runner, repo=repo, repository=repository)
    if refusal is not None:
        return refusal
    successor = replace(
        reading.attempt,
        phase=DRILL_CLOSED,
        operation_id=f"{reading.attempt.attempt_id}#drill-close",
        generation=reading.attempt.generation + 1,
        repayment_required=False,
    )
    committed = commit_transition(
        client=client, observed=reading, successor=successor, allow_drill_close=True
    )
    if isinstance(committed, AuthorityRefusal):
        return committed
    current = require_current_generation(client=client, observed=committed)
    if isinstance(current, AuthorityRefusal):
        return current
    result = change_claim(
        client=client,
        work_item_id=committed.attempt.item_id,
        writer="incident-drill-close",
        intent="drill-close",
        claim_tokens=True,
        status=lifecycle_state_for(phase=DRILL_CLOSED) or "",
        clear_assignee=True,
        still_as_decided=lambda row: row.get("status") == "active",
    )
    if result.outcome != "applied":
        return _refuse(code="incident-drill-close-lifecycle-refused", detail=result.outcome)
    return DrillClose(
        reading=committed,
        lifecycle_state=lifecycle_state_for(phase=DRILL_CLOSED) or "",
        repayment_outstanding=False,
    )
