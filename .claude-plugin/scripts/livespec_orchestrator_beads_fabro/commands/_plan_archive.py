"""The archive leg of the plan operation: the gates, the close, and the move.

Split out of `plan.py` by cohesion. That module holds the AUTHORING concern —
creating a plan, appending a handoff entry, recording a scope event — and this
one holds ARCHIVING, which is a different responsibility with a different
neighbourhood: `_plan_archive_gates` supplies the working-tree sweep and
`_plan_archive_review` supplies the completeness-review evidence rules, and
both were imported into `plan.py` for this leg alone.

The split cuts at the public entry point. `archive_thread` moves together with
the two private helpers only IT used, so nothing private crosses a module
boundary; `plan.py` imports the public name back and re-exports it, leaving
every existing caller of `plan.archive_thread` unaffected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
    outside_plan_path_references,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
    ArchiveCompletenessReviewRequest,
    CompletenessReviewLauncher,
    archive_completeness_review_request,
    undisposed_plan_child_ids,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    last_carrier_map_position,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_identity import (
    ARCHIVING_PARTY,
    completeness_leg_identity,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    plan_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_leg import (
    PlanProofLeg,
    plan_proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import plan_proof_entries
from livespec_orchestrator_beads_fabro.commands._plan_release_tags import (
    repository_release_tags,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    plan_comment_body,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "PLAN_ARCHIVE_ACTOR",
    "archive_thread",
    "resolve_plan_proof_leg",
]

_PLAN_DIR = "plan"
_ARCHIVE_DIR = "archive"
# The reserved author literal the archive leg signs its own handoff entry with,
# computed here rather than accepted from a caller — the same reservation
# `append_supervisor_handoff` makes for `<slug>-supervisor`. It is the TIMELINE
# AUTHOR word and nothing else: it was once also the value the completeness leg
# compared a reviewer identity against, which is the defect `bd-ib-3xsz` records,
# and that comparand is now the archiving party's COMPUTED identity
# (`_plan_completeness_identity`).
PLAN_ARCHIVE_ACTOR = "plan-archive"


def archive_thread(  # noqa: PLR0913 — package primitive mirrors the archive inputs.
    *,
    project_root: Path,
    config: StoreConfig,
    slug: str,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None = None,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, str]:
    """Archive a thread once the child, working-tree, review and proof gates pass.

    The working-tree gate sits between the two original ledger gates
    deliberately. It is mechanical and cheap, like the child-disposition leg,
    so a plan the move would break refuses BEFORE a fresh independent reviewer
    is commissioned — and, decisively, before the epic is closed and stamped.

    THE PROOF LEG RUNS LAST, in the ratified enumeration's own order. It is a
    cheap ledger read and could have gone earlier on the economy argument the
    working-tree sweep is placed on — but the clause names it third, and the
    same clause says the independent completeness reviewer MAY be the verifying
    party of the plan Proof of Done record, which only reads sensibly if the
    review resolves first. What matters for correctness is that it runs before
    the move and the close, not where it sits among the refusals.

    THE ARCHIVING PARTY'S IDENTITY IS COMPUTED, and `env`/`runner` are the two
    seams that computation reads — never an identity a caller could supply. It is
    resolved AFTER the two cheap mechanical gates and before the review leg
    because it is that leg's own comparand: a plan refusing for undisposed
    children owes nobody a forge round trip, and a leg comparing two identities
    cannot run before one of them exists.
    """
    client = make_beads_client(config=config)
    undisposed = list(undisposed_plan_child_ids(client=client, epic_id=epic_id))
    if undisposed:
        raise PlanArchiveRefusedError.undisposed_children(child_ids=undisposed)
    referencing = outside_plan_path_references(project_root=project_root, slug=slug)
    if referencing:
        raise PlanArchiveRefusedError.outside_path_references(slug=slug, paths=referencing)
    archive_identity = completeness_leg_identity(
        role=ARCHIVING_PARTY,
        project_root=project_root,
        env=env,
        runner=runner,
    )
    source = project_root / _PLAN_DIR / slug
    evidence_id = _resolve_completeness_review_evidence(
        client=client,
        epic_id=epic_id,
        completeness_review_comment_id=completeness_review_comment_id,
        review_launcher=review_launcher,
        archive_identity=archive_identity,
        request=archive_completeness_review_request(
            client=client,
            project_root=project_root,
            source=source,
            slug=slug,
            epic_id=epic_id,
        ),
    )
    if evidence_id is None:
        raise PlanArchiveRefusedError.missing_completeness_review()
    proof = resolve_plan_proof_leg(client=client, project_root=project_root, epic_id=epic_id)
    if not proof.met:
        raise PlanArchiveRefusedError.unproved_plan_assertions(
            unproved=proof.unproved,
            rejected=proof.rejected,
        )
    archive = project_root / _PLAN_DIR / _ARCHIVE_DIR / slug
    archive.parent.mkdir(parents=True, exist_ok=True)
    _ = source.rename(archive)
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_HANDOFF_PREFIX,
            author=PLAN_ARCHIVE_ACTOR,
            now=_utc_now_iso(),
            body=f"Archived after completeness review {evidence_id}.",
        ),
    )
    client.close_issue(issue_id=epic_id, reason="plan archived")
    return {"archive_path": archive.relative_to(project_root).as_posix(), "epic_id": epic_id}


def resolve_plan_proof_leg(
    *, client: BeadsClient, project_root: Path, epic_id: str
) -> PlanProofLeg:
    """Gather the proof leg's four inputs from this epic and grade it.

    PUBLIC because the `plan` front-end reports the leg before it attempts an
    archive, and because the plan-record conformance check grades the same
    records: a second gather would read the timeline twice and could answer
    differently while both answers looked well-formed.

    ONE comment read feeds three of the four inputs — the records, their append
    positions, and where the last carrier-map event sits — so the positions the
    leg compares all come from the same list. Reading the timeline twice is the
    way those indices come to be measured against different lists.

    A missing Definition of Done section refuses HERE rather than grading an
    empty assertion set, because zero assertions means zero unproved ones: the
    leg would report met, and a plan with no stated definition of done would
    archive on the strength of having nothing to prove.
    """
    description = client.show_issue(issue_id=epic_id).get("description")
    section = plan_definition_of_done(
        description=description if isinstance(description, str) else ""
    )
    if section.criteria_text is None:
        raise PlanArchiveRefusedError.missing_plan_definition_of_done(epic_id=epic_id)
    comments = client.list_comments(issue_id=epic_id)
    return plan_proof_leg(
        assertions=section.assertions,
        entries=plan_proof_entries(comments=comments),
        carrier_map_position=last_carrier_map_position(comments=comments),
        release_tags=repository_release_tags(project_root=project_root),
    )


def _resolve_completeness_review_evidence(
    *,
    client: BeadsClient,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None,
    archive_identity: str,
    request: ArchiveCompletenessReviewRequest,
) -> str | None:
    evidence_id = _accepted_evidence_id(
        client=client,
        epic_id=epic_id,
        candidate=completeness_review_comment_id,
        archive_identity=archive_identity,
        current_child_ids=request.child_ids,
    )
    if evidence_id is not None or review_launcher is None:
        return evidence_id
    return _accepted_evidence_id(
        client=client,
        epic_id=epic_id,
        candidate=review_launcher(request=request),
        archive_identity=archive_identity,
        current_child_ids=request.child_ids,
    )


def _accepted_evidence_id(
    *,
    client: BeadsClient,
    epic_id: str,
    candidate: str | None,
    archive_identity: str,
    current_child_ids: tuple[str, ...],
) -> str | None:
    """The candidate evidence id the leg accepts, refusing outright on a self-review.

    The SELF-REVIEW arm raises from here rather than returning `None` up to the
    caller's generic refusal, and it raises before the launcher is consulted:
    commissioning a fresh reviewer is the remedy for evidence that is MISSING,
    and a plan whose evidence was authored by the archiving party needs a
    different PARTY rather than another round of the same one.
    """
    if candidate is None:
        return None
    evidence = completeness_review_evidence(
        client=client,
        epic_id=epic_id,
        evidence_id=candidate,
        archive_identity=archive_identity,
        current_child_ids=current_child_ids,
    )
    if evidence.self_review_identity is not None:
        raise PlanArchiveRefusedError.self_reviewed_completeness(
            identity=evidence.self_review_identity,
            evidence_id=candidate,
        )
    return evidence.accepted_id


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
