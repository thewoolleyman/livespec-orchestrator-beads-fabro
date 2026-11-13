"""Fresh forge evidence that a retained incident chain is a recorded drill."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
)
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_recovery_plan import RECOVERY_MARKER
from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["recorded_drill_evidence"]

_SCRATCH = "incident-scratch/"
_NOT_A_DRILL = "incident-not-a-recorded-drill"
_UNAVAILABLE = "incident-drill-evidence-unavailable"


def _refusal(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _carriers(
    *, history: tuple[IncidentAttempt, ...]
) -> tuple[IncidentAttempt, ...] | AuthorityRefusal:
    latest: dict[str, IncidentAttempt] = {}
    for attempt in history:
        carrier = attempt.carrier
        if carrier is None:
            return _refusal(
                code=_NOT_A_DRILL, detail=f"attempt {attempt.attempt_id} has no carrier"
            )
        latest[carrier.target_ref] = attempt
    for attempt in latest.values():
        carrier = attempt.carrier
        if not isinstance(carrier, PrBound) or attempt.pr_number <= 0:
            detail = attempt.attempt_id if carrier is None else carrier.target_ref
            return _refusal(
                code=_NOT_A_DRILL,
                detail=f"carrier {detail} is not bound to a pull request",
            )
    return tuple(latest.values())


def _carrier_evidence(
    *, carriers: tuple[IncidentAttempt, ...], runner: CommandRunner, repo: Path, repository: str
) -> AuthorityRefusal | None:
    """Read each distinct recorded carrier pull request from the forge."""
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
            return _refusal(code=_UNAVAILABLE, detail=f"PR #{attempt.pr_number}: forge read failed")
        pull = cast("dict[str, object]", value)
        if (
            pull.get("number") != attempt.pr_number
            or not isinstance(pull.get("state"), str)
            or not isinstance(pull.get("baseRefName"), str)
        ):
            return _refusal(
                code=_UNAVAILABLE, detail=f"PR #{attempt.pr_number}: forge read incomplete"
            )
        if pull["state"] != "MERGED" or not cast("str", pull["baseRefName"]).startswith(_SCRATCH):
            carrier = attempt.carrier
            return _refusal(
                code=_NOT_A_DRILL,
                detail=f"carrier {attempt.attempt_id if carrier is None else carrier.target_ref}",
            )
    return None


def _revert_commits(*, client: BeadsClient, item_id: str) -> tuple[str, ...]:
    """Every revert commit a retained revert receipt or rollback release recorded."""
    commits: dict[str, None] = {}
    for row in client.list_comments(issue_id=item_id):
        text = row.get("text")
        if not isinstance(text, str) or not text.startswith(RECOVERY_MARKER):
            continue
        record = parse_json(text=text[len(RECOVERY_MARKER) :])
        if not isinstance(record, dict):
            continue
        body = cast("dict[str, object]", record)
        if body.get("kind") != "revert-receipt":
            continue
        for key in ("receipt", "resolution"):
            detail = body.get(key)
            receipt = cast("dict[str, object]", detail) if isinstance(detail, dict) else None
            commit = receipt.get("revert_commit") if receipt is not None else None
            if isinstance(commit, str) and commit:
                commits.setdefault(commit)
    return tuple(commits)


def _recorded_commits(
    *, client: BeadsClient, item_id: str, history: tuple[IncidentAttempt, ...]
) -> tuple[tuple[str, str], ...]:
    """Each retained commit the chain could have put on master, labelled by kind."""
    landed = (("landed", commit) for attempt in history for commit in attempt.landed_commits)
    reverts = (("revert", commit) for commit in _revert_commits(client=client, item_id=item_id))
    return (*landed, *reverts)


def _landed_evidence(
    *, commits: tuple[tuple[str, str], ...], runner: CommandRunner, repo: Path, repository: str
) -> AuthorityRefusal | None:
    """Refuse a drill if any retained landed or revert commit is already reachable from master."""
    for kind, commit in commits:
        result = runner.run(
            argv=["gh", "api", f"repos/{repository}/compare/{commit}...master", "--method", "GET"],
            cwd=repo,
            timeout_seconds=60.0,
        )
        value = parse_json(text=result.stdout) if result.exit_code == 0 else None
        if not isinstance(value, dict):
            return _refusal(code=_UNAVAILABLE, detail=f"commit {commit}: unreadable")
        comparison = cast("dict[str, object]", value)
        behind = comparison.get("behind_by")
        if not isinstance(behind, int) or behind < 0:
            return _refusal(code=_UNAVAILABLE, detail=f"commit {commit}: incomplete")
        # In `commit...master`, no commits behind means master already contains
        # the recorded commit (or is that exact commit).  A divergent master is
        # allowed only when it still lacks at least this recorded commit.
        if behind == 0:
            return _refusal(code=_NOT_A_DRILL, detail=f"{kind} commit {commit}")
    return None


def recorded_drill_evidence(
    *,
    client: BeadsClient,
    item_id: str,
    history: tuple[IncidentAttempt, ...],
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> AuthorityRefusal | None:
    """Return the first named reason the immutable chain is not a recorded drill."""
    carriers = _carriers(history=history)
    if isinstance(carriers, AuthorityRefusal):
        return carriers
    return _carrier_evidence(
        carriers=carriers, runner=runner, repo=repo, repository=repository
    ) or _landed_evidence(
        commits=_recorded_commits(client=client, item_id=item_id, history=history),
        runner=runner,
        repo=repo,
        repository=repository,
    )
