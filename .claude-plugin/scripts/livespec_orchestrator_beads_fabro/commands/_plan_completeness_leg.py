"""Resolving the archive's completeness leg: grade, commission, accept or refuse.

Split out of `_plan_archive` by cohesion when the recency binding (`bd-ib-0pf5`)
pushed that module past its LLOC ceiling. `_plan_archive` holds the ARCHIVE
SEQUENCE — the four gates in their ratified order, the epic close and the
directory move — while this module holds the whole of leg two: which recorded
evidence counts, when a fresh reviewer is commissioned, and which of the three
refusals the leg owes when none counts.

The split cuts at ONE public entry point. `accepted_completeness_review_evidence`
either returns the accepted id or raises the leg's own refusal, so every private
helper the leg needs moves with it and nothing private crosses a module boundary.
Returning a verdict for the caller to re-interpret would have left the refusal
CHOICE in `_plan_archive`, which is the half most likely to drift: three states
with three different remedies, decided one module away from the grade that
distinguishes them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    CompletenessReviewEvidence,
    completeness_review_evidence,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
        ArchiveCompletenessReviewRequest,
        CompletenessReviewLauncher,
    )
    from livespec_orchestrator_beads_fabro.commands._plan_completeness_recency import (
        PlanChildStatus,
        StaleEvidenceReport,
    )

__all__: list[str] = [
    "accepted_completeness_review_evidence",
]


def accepted_completeness_review_evidence(  # noqa: PLR0913 — mirrors the leg's inputs.
    *,
    client: BeadsClient,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None,
    archive_identity: str,
    children: tuple[PlanChildStatus, ...],
    request: ArchiveCompletenessReviewRequest,
) -> str:
    """The evidence id this leg accepts, or the refusal it owes instead.

    `children` and `request.child_ids` are the SAME membership read, threaded in
    from the archive sequence rather than re-derived here, so the brief a
    commissioned reviewer receives and the grade its record is held to cannot
    disagree.
    """
    evidence = _resolved_evidence(
        client=client,
        epic_id=epic_id,
        completeness_review_comment_id=completeness_review_comment_id,
        review_launcher=review_launcher,
        archive_identity=archive_identity,
        children=children,
        request=request,
    )
    if evidence.accepted_id is None:
        raise _leg_refusal(stale=evidence.stale)
    return evidence.accepted_id


def _resolved_evidence(  # noqa: PLR0913 — mirrors the leg's inputs.
    *,
    client: BeadsClient,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None,
    archive_identity: str,
    children: tuple[PlanChildStatus, ...],
    request: ArchiveCompletenessReviewRequest,
) -> CompletenessReviewEvidence:
    """Grade the recorded evidence, commissioning one fresh review when none is valid.

    STALE evidence is commissioned around exactly as MISSING evidence is: the
    ratified clause asks for a fresh independent reviewer whenever the timeline
    carries no VALID evidence, and a record that no longer covers the plan is not
    valid evidence. Refusing on sight would leave every stale plan waiting on a
    human to notice the gap, which is the thing commissioning exists to retire.

    When the commissioned reviewer records nothing the leg can read — the common
    case, since a review takes longer than the attempt that asked for it — the
    FIRST read's stale account is returned rather than the second's empty one.
    The refusal is the caller's whole explanation, and an attempt reporting
    "evidence is required" here would hide the records it had just read and
    rejected.
    """
    graded = _graded_evidence(
        client=client,
        epic_id=epic_id,
        candidate=completeness_review_comment_id,
        archive_identity=archive_identity,
        children=children,
    )
    if graded.accepted_id is not None or review_launcher is None:
        return graded
    fresh = _graded_evidence(
        client=client,
        epic_id=epic_id,
        candidate=review_launcher(request=request),
        archive_identity=archive_identity,
        children=children,
    )
    if fresh.accepted_id is None and not fresh.stale:
        return graded
    return fresh


def _graded_evidence(
    *,
    client: BeadsClient,
    epic_id: str,
    candidate: str | None,
    archive_identity: str,
    children: tuple[PlanChildStatus, ...],
) -> CompletenessReviewEvidence:
    """How this candidate graded, refusing outright on a self-review.

    The SELF-REVIEW arm raises from here rather than riding back as a verdict,
    and it raises before the launcher is consulted: commissioning a fresh
    reviewer is the remedy for evidence that is missing or stale, and a plan
    whose evidence was authored by the archiving party needs a different PARTY
    rather than another round of the same one.
    """
    if candidate is None:
        return CompletenessReviewEvidence(
            accepted_id=None,
            self_review_identity=None,
            stale=(),
        )
    evidence = completeness_review_evidence(
        client=client,
        epic_id=epic_id,
        evidence_id=candidate,
        archive_identity=archive_identity,
        children=children,
    )
    if evidence.self_review_identity is not None:
        raise PlanArchiveRefusedError.self_reviewed_completeness(
            identity=evidence.self_review_identity,
            evidence_id=candidate,
        )
    return evidence


def _leg_refusal(*, stale: tuple[StaleEvidenceReport, ...]) -> PlanArchiveRefusedError:
    """The refusal this leg owes when no candidate was accepted.

    Two refusals rather than one, because the two states prescribe different next
    actions: nothing recorded needs a review somebody still has to perform, while
    a stale record needs a review of the plan as it NOW stands and a reader told
    only that evidence is required would go looking for a record already on the
    timeline.
    """
    if stale:
        return PlanArchiveRefusedError.stale_completeness_review(reports=stale)
    return PlanArchiveRefusedError.missing_completeness_review()
