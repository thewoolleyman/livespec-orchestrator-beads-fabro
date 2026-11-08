"""The `bind-repayment-acceptance` action: bind the merged repayment PR as the forge reports it.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle". The
repayment opens on its own `branch-reserved` carrier at `repayment-admission`
and walks to `repayment-active` with no PR; `advance-repayment` changes only
the phase and generation, so it cannot bind the PR the factory run merged. This
action does, without trusting a caller-typed result:

- the PR's number, state, head branch, head commit and merge commit come from
  `gh pr view`; a PR that is not `MERGED` is refused, as is one whose head
  branch is not the carrier's reserved ref;
- the landed commits and their trees are read from git over the merge commit's
  first-parent history after fetching it: a rebase merge lands one commit per
  PR commit, oldest first, and a squash or merge commit lands the merge commit
  alone.

The successor is `repayment-acceptance` on the same attempt, bound to that PR
with a `pr-bound` carrier whose remote head is the PR head, committed through
the canonical transition writer, so a stale or superseded observation records
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_carrier import (
    BranchReserved,
    HeadPublished,
    PrBound,
    is_object_id,
)
from livespec_orchestrator_beads_fabro._incident_phases import (
    REPAYMENT_PHASES,
    lifecycle_state_for,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_authority import commit_incident_transition
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "CARRIER_MISMATCH",
    "LANDED_UNOBSERVABLE",
    "PR_UNMERGED",
    "PR_UNOBSERVABLE",
    "MergedRepayment",
    "bind_repayment_acceptance",
    "observe_merged_repayment",
]

PR_UNOBSERVABLE = "incident-repayment-pr-unobservable"
PR_UNMERGED = "incident-repayment-pr-unmerged"
CARRIER_MISMATCH = "incident-repayment-carrier-mismatch"
LANDED_UNOBSERVABLE = "incident-repayment-landed-unobservable"
_STALE = "incident-repayment-stale-observation"
_PHASE_ORDER = "incident-repayment-phase-order"
_STATE_MISMATCH = "incident-phase-state-mismatch"
_ACTIVE = REPAYMENT_PHASES[2]
_ACCEPTANCE = REPAYMENT_PHASES[3]
_PR_FIELDS = "number,state,headRefName,headRefOid,mergeCommit,commits"
_MERGED = "MERGED"
_REFS_HEADS = "refs/heads/"
_LOG_FORMAT = "%H%x00%T%x00%P%x00%s"
_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class MergedRepayment:
    """One merged PR as the forge and the landed history report it."""

    number: int
    head_ref: str
    head: str
    landed_commits: tuple[str, ...]
    landed_trees: tuple[str, ...]


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _headlines(*, value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    rows = [
        cast("dict[str, object]", row)
        for row in cast("list[object]", value)
        if isinstance(row, dict)
    ]
    lines = tuple(row.get("messageHeadline") for row in rows)
    return cast("tuple[str, ...]", lines) if all(isinstance(v, str) for v in lines) else None


def _landed(
    *, runner: CommandRunner, repo: Path, merge: str, headlines: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """The landed commits and trees, oldest first; None when the history cannot be read."""
    _ = runner.run(
        argv=["git", "fetch", "--quiet", "--no-tags", "origin", merge],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    result = runner.run(
        argv=[
            "git",
            "log",
            "--first-parent",
            f"--format={_LOG_FORMAT}",
            "-n",
            str(len(headlines)),
            merge,
        ],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    rows = [line.split("\x00") for line in result.stdout.splitlines() if line]
    if result.exit_code != 0 or not rows or any(len(row) != 4 for row in rows):  # noqa: PLR2004
        return None
    if rows[0][0] != merge or not all(is_object_id(value=v) for row in rows for v in row[:2]):
        return None
    oldest_first = rows[::-1]
    rebased = len(rows[0][2].split()) == 1 and tuple(row[3] for row in oldest_first) == headlines
    landed = oldest_first if rebased else rows[:1]
    return tuple(row[0] for row in landed), tuple(row[1] for row in landed)


def observe_merged_repayment(
    *, runner: CommandRunner, repo: Path, repository: str, pr_number: int
) -> MergedRepayment | AuthorityRefusal:
    """The named PR as merged on the forge, with its landed history; anything else refuses."""
    result = runner.run(
        argv=["gh", "pr", "view", str(pr_number), "--repo", repository, "--json", _PR_FIELDS],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    number, state = value.get("number"), value.get("state")
    head_ref, head = value.get("headRefName"), value.get("headRefOid")
    headlines = _headlines(value=value.get("commits"))
    if (
        number != pr_number
        or type(number) is not int
        or not isinstance(state, str)
        or not isinstance(head_ref, str)
        or not is_object_id(value=head)
        or headlines is None
    ):
        reason = result.stderr.strip() or "no number, state, head and commits in the reply"
        return _refuse(code=PR_UNOBSERVABLE, detail=f"PR #{pr_number}: {reason}")
    merge_commit = value.get("mergeCommit")
    merge = (
        cast("dict[str, object]", merge_commit).get("oid")
        if isinstance(merge_commit, dict)
        else None
    )
    if state != _MERGED or not is_object_id(value=merge):
        return _refuse(code=PR_UNMERGED, detail=f"PR #{pr_number}: {state}")
    landed = _landed(runner=runner, repo=repo, merge=cast("str", merge), headlines=headlines)
    if landed is None:
        return _refuse(code=LANDED_UNOBSERVABLE, detail=f"PR #{pr_number}: merge {merge}")
    return MergedRepayment(
        number=number,
        head_ref=head_ref,
        head=cast("str", head),
        landed_commits=landed[0],
        landed_trees=landed[1],
    )


def _precondition(*, client: BeadsClient, reading: IncidentReading) -> AuthorityRefusal | None:
    """Why the named attempt cannot take a PR binding now, before the forge is read."""
    attempt = reading.attempt
    if not reading.is_current:
        return _refuse(code=_STALE, detail=attempt.item_id)
    if attempt.phase != _ACTIVE:
        return _refuse(code=_PHASE_ORDER, detail=f"{attempt.phase} -> {_ACCEPTANCE}")
    if not isinstance(attempt.carrier, BranchReserved | HeadPublished):
        return _refuse(code=CARRIER_MISMATCH, detail=f"{attempt.item_id}: no reserved carrier")
    state = lifecycle_state_for(phase=_ACCEPTANCE)
    status = client.show_issue(issue_id=attempt.item_id).get("status")
    if status != state:
        return _refuse(
            code=_STATE_MISMATCH,
            detail=f"{_ACCEPTANCE} pairs with {state}, item rests at {status}",
        )
    return None


def bind_repayment_acceptance(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    pr_number: int,
) -> RepaymentEntry | AuthorityRefusal:
    """Record `repayment-acceptance` bound to the merged repayment PR the forge reports."""
    refusal = _precondition(client=client, reading=reading)
    if refusal is not None:
        return refusal
    merged = observe_merged_repayment(
        runner=runner, repo=repo, repository=repository, pr_number=pr_number
    )
    if isinstance(merged, AuthorityRefusal):
        return merged
    attempt = reading.attempt
    carrier = cast("BranchReserved | HeadPublished", attempt.carrier)
    if _REFS_HEADS + merged.head_ref != carrier.target_ref:
        return _refuse(
            code=CARRIER_MISMATCH,
            detail=f"PR #{pr_number} head {merged.head_ref} is not {carrier.target_ref}",
        )
    successor = replace(
        attempt,
        phase=_ACCEPTANCE,
        operation_id=f"{attempt.attempt_id}#{_ACCEPTANCE}",
        generation=attempt.generation + 1,
        head=merged.head,
        pr_number=merged.number,
        landed_commits=merged.landed_commits,
        landed_trees=merged.landed_trees,
        carrier=PrBound(
            target_ref=carrier.target_ref,
            input_parent=carrier.input_parent,
            staged_tree=carrier.staged_tree,
            remote_head=merged.head,
        ),
    )
    committed = commit_incident_transition(client=client, observed=reading, successor=successor)
    if isinstance(committed, AuthorityRefusal):
        return committed
    return RepaymentEntry(
        reading=committed,
        operation_id=attempt.attempt_id,
        lifecycle_state=lifecycle_state_for(phase=_ACCEPTANCE) or "",
        recovered=False,
    )
