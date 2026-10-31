"""The plan-epic ledger-comment arm of the typed verified-proof reader."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_VERIFIED
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_REPLAY_VERDICTS,
    latest_plan_proof_entry,
    plan_proof_entries,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_LEDGER,
    ResultObservation,
    satisfied,
    unobservable,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    result_store_config,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment

__all__: list[str] = ["observe_plan_verified_proof"]

_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    BeadsConnectionError,
    BeadsCommandError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def observe_plan_verified_proof(
    *, repository: ResultRepository, target: VerifiedProofTarget, now: str
) -> ResultObservation:
    """Read a plan epic's latest deciding proof record from its ledger comments."""
    comments = _read_comments(repository=repository, target=target, now=now)
    if isinstance(comments, ResultObservation):
        return comments
    entries = plan_proof_entries(comments=tuple({"text": one.text} for one in comments))
    latest = latest_plan_proof_entry(entries=entries, verdicts=PLAN_REPLAY_VERDICTS)
    if latest is None:
        return _unsatisfied(
            repository=repository,
            target=target,
            now=now,
            evidence=f"{len(comments)} ledger comment(s) read on {target.subject_id}",
            detail=(
                f"no verified or not_reproduced plan Proof of Done record was read on"
                f" plan epic {target.subject_id}"
            ),
        )
    comment = comments[latest.position]
    evidence = (
        f"ledger comment {_comment_identity(comment=comment, position=latest.position)}"
        f" on {target.subject_id}"
    )
    if latest.record.verdict != VERDICT_VERIFIED:
        return _unsatisfied(
            repository=repository,
            target=target,
            now=now,
            evidence=evidence,
            detail=(
                f"the latest verdict-bearing plan Proof of Done record on {target.subject_id}"
                f" is {latest.record.verdict}, not verified"
            ),
        )
    identity = build_identity_in(body=latest.record.body)
    if identity is None or identity.containment_ref != target.build:
        return _unsatisfied(
            repository=repository,
            target=target,
            now=now,
            evidence=evidence,
            detail=(
                f"the verified plan Proof of Done record on {target.subject_id} does not"
                f" name required build {target.build}"
            ),
        )
    missing = tuple(
        assertion
        for assertion in target.assertions
        if latest.record.reproduced(assertion=assertion) is not True
    )
    if missing:
        return _unsatisfied(
            repository=repository,
            target=target,
            now=now,
            evidence=evidence,
            detail=(
                f"the verified plan Proof of Done record on {target.subject_id} does not"
                f" reproduce {len(missing)} of the {len(target.assertions)} requested"
                " assertion(s)"
            ),
        )
    return satisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_LEDGER,
        now=now,
        evidence=evidence,
        detail=(
            f"the verified plan Proof of Done record on {target.subject_id} names build"
            f" {target.build} and reproduces every requested assertion"
        ),
    )


def _read_comments(
    *, repository: ResultRepository, target: VerifiedProofTarget, now: str
) -> tuple[WorkItemComment, ...] | ResultObservation:
    """Read the epic timeline, keeping an unreadable ledger distinct from no proof."""
    config = result_store_config(repository=repository)
    if config is None:
        return unobservable(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_LEDGER,
            now=now,
            detail="the named repository's own configuration did not resolve a tenant connection",
        )
    read = attempt(
        action=lambda: read_work_item_comments(path=config, work_item_id=target.subject_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return unobservable(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_LEDGER,
            now=now,
            detail=(
                f"the ledger comment read of plan epic {target.subject_id} failed:"
                f" {type(read.error).__name__}: {read.error}"
            ),
        )
    return tuple(read)


def _unsatisfied(
    *,
    repository: ResultRepository,
    target: VerifiedProofTarget,
    now: str,
    evidence: str,
    detail: str,
) -> ResultObservation:
    return unsatisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_LEDGER,
        now=now,
        evidence=evidence,
        detail=detail,
    )


def _comment_identity(*, comment: WorkItemComment, position: int) -> str:
    """The ledger identity a plan-proof observation cites."""
    return comment.comment_id or comment.created_at or f"position {position + 1}"
