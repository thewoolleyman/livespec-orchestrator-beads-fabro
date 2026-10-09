"""The completeness-review evidence record: how one is written, and what it is worth.

Split out of `_plan_archive_review` by cohesion. That module holds the plan
MEMBERSHIP concern — which linked members the archive gate counts as undisposed,
and the request context a fresh reviewer is handed — and this one holds the
EVIDENCE RECORD: the comment a reviewer writes, the parse that reads it back, and
the grade that decides whether it satisfies the completeness leg.

The split cuts at the public entry points, and it deliberately keeps the RENDER
beside the PARSE. Both halves of one comment format now live in one module and are
structurally incapable of drifting apart; splitting authoring from grading would
have put them in different files, which is the same trap `_plan_timeline` was
assembled to close for the plan handoff header.

WHAT THIS GATE VERIFIES, AND WHAT IT MERELY RECORDS — stated here because a reader
of a PASSING gate would otherwise infer enforcement that is absent. Of the four
fields an evidence comment carries, exactly ONE is cross-checked against anything
its author does not control. `reviewer-identity` is COMPUTED by
`_plan_completeness_identity` from the reviewing session's own environment, and the
archive leg compares it against the ARCHIVING session's identity computed by the
same resolver; that comparison is the whole of the independence guarantee.

`separate-reviewer` and `attests-complete-requirement-coverage` are SELF-DECLARED
ATTESTATIONS. The party that authored the comment set both, nothing cross-checks
either, and no reading of a passing gate establishes that either claim is true.
They are recorded for two reasons that do not require verification: a reviewer
unwilling to make the claim leaves a comment that does not satisfy the leg, and an
audit can read afterwards what was claimed and by whom. What the gate establishes
is that the two attestations WERE made, and that the party who made them is not
the party archiving.

THE ONE BEHAVIOUR THE COMPUTED IDENTITY RELAXES, named here rather than left to be
discovered. Until the comparand became the archiving party's computed identity,
the grade excluded the reserved literal `plan-archive`. That literal is no longer
excluded: it differs from every computed identity, so a legacy comment carrying it
is now accepted. Nothing written through this primitive can carry it — the
identity is computed, and the reserved word is not an identity any runtime
exports — so the relaxation reaches only comments hand-authored under the old
convention on a plan that has not yet archived. No archive that has already
happened is re-graded: the leg runs at archive time and nothing re-runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from typing_extensions import Unpack

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_completeness_identity import (
    REVIEWING_PARTY,
    completeness_leg_identity,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CompletenessReviewEvidence",
    "CompletenessReviewEvidenceFields",
    "completeness_review_evidence",
    "record_completeness_review_evidence",
]

_PLAN_COMPLETENESS_REVIEW_PREFIX = "plan-completeness-review-evidence"
_TRUE = "true"


class CompletenessReviewEvidenceFields(TypedDict):
    """Keyword payload for a durable completeness-review evidence record.

    There is NO `reviewer_identity` field, and that absence is the guarantee
    rather than an omission: the identity is computed from the reviewing session's
    own environment, so a caller supplies only what it alone holds — which record
    this is, what it attests, and the prose behind the attestation.
    """

    evidence_id: str
    separate_reviewer: bool
    attests_complete_requirement_coverage: bool
    body: str
    now: str


@dataclass(frozen=True, kw_only=True)
class CompletenessReviewEvidence:
    """How one candidate evidence id graded against the archiving party's identity.

    TWO fields rather than one optional id, because the two failures prescribe
    different next actions and nothing at the surface distinguishes them. A
    missing, malformed or non-attesting comment needs a review somebody still has
    to perform and record. A comment whose reviewer identity EQUALS the archiving
    session's needs a DIFFERENT party to perform it — and an archive reporting
    only "evidence is required" would send the one session that cannot satisfy
    this leg back to author a second comment under the same identity.
    """

    accepted_id: str | None
    self_review_identity: str | None


def record_completeness_review_evidence(
    *,
    config: StoreConfig,
    epic_id: str,
    project_root: Path | None = None,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
    **evidence: Unpack[CompletenessReviewEvidenceFields],
) -> None:
    """Append a durable plan completeness-review evidence comment.

    `project_root`, `env` and `runner` are the seams the reviewer's identity is
    COMPUTED through, and the ordinary in-session call supplies none of them. They
    are not an identity route: there is no field a caller can put a name in, which
    is what keeps the archive leg's self-review refusal from being one keyword
    away from passing.

    The identity resolves BEFORE the append, so an invocation that cannot name its
    reviewer writes nothing. A record comment must not be edited after posting —
    a correction is a new record — so an evidence comment naming no reviewer would
    sit on the timeline permanently, where the archive gate would read it, decline
    to count it, and report a refusal whose cause the reviewer could not see from
    its own successful write.
    """
    reviewer_identity = completeness_leg_identity(
        role=REVIEWING_PARTY,
        project_root=project_root,
        env=env,
        runner=runner,
    )
    client = make_beads_client(config=config)
    client.add_comment(
        issue_id=epic_id,
        body=_evidence_comment_body(
            evidence_id=evidence["evidence_id"],
            reviewer_identity=reviewer_identity,
            separate_reviewer=evidence["separate_reviewer"],
            attests_complete_requirement_coverage=evidence["attests_complete_requirement_coverage"],
            body=evidence["body"],
            now=evidence["now"],
        ),
    )


def completeness_review_evidence(
    *,
    client: BeadsClient,
    epic_id: str,
    evidence_id: str,
    archive_identity: str,
) -> CompletenessReviewEvidence:
    """Grade this epic's evidence comments for `evidence_id` against the archiver.

    The FIRST attesting comment whose reviewer is not the archiving party wins,
    and a self-review is REMEMBERED rather than returned on sight: two comments
    can carry one evidence id, and refusing on the first one read would refuse an
    archive that a later, genuinely independent comment satisfies.
    """
    self_review_identity: str | None = None
    for comment in client.list_comments(issue_id=epic_id):
        text = comment.get("text")
        if not isinstance(text, str):
            continue
        reviewer = _attesting_reviewer(fields=_evidence_fields(text=text), evidence_id=evidence_id)
        if reviewer is None:
            continue
        if reviewer != archive_identity:
            return CompletenessReviewEvidence(accepted_id=evidence_id, self_review_identity=None)
        self_review_identity = reviewer
    return CompletenessReviewEvidence(accepted_id=None, self_review_identity=self_review_identity)


def _evidence_comment_body(
    *,
    evidence_id: str,
    reviewer_identity: str,
    separate_reviewer: bool,
    attests_complete_requirement_coverage: bool,
    body: str,
    now: str,
) -> str:
    separate = str(separate_reviewer).lower()
    coverage = str(attests_complete_requirement_coverage).lower()
    return (
        f"{_PLAN_COMPLETENESS_REVIEW_PREFIX}\n"
        f"evidence-id: {evidence_id}\n"
        f"reviewer-identity: {reviewer_identity}\n"
        f"separate-reviewer: {separate}\n"
        f"attests-complete-requirement-coverage: {coverage}\n"
        f"timestamp: {now}\n\n"
        f"{body}"
    )


def _evidence_fields(*, text: str) -> dict[str, str]:
    header = text.split("\n\n", maxsplit=1)[0]
    lines = header.splitlines()
    if not lines or lines[0] != _PLAN_COMPLETENESS_REVIEW_PREFIX:
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition(": ")
        if separator == "":
            return {}
        fields[key] = value
    return fields


def _attesting_reviewer(*, fields: dict[str, str], evidence_id: str) -> str | None:
    """The reviewer this comment names, when it is the right record and fully attests.

    `None` for every comment the leg cannot count, which is deliberately the same
    answer for an unrelated comment, a malformed header, the wrong evidence id, an
    absent reviewer identity, and either attestation withheld. The caller needs no
    finer distinction among those: none of them is evidence, and the remedy for
    every one is the same recorded review.
    """
    reviewer_identity = fields.get("reviewer-identity")
    attests = (
        fields.get("evidence-id") == evidence_id
        and fields.get("separate-reviewer") == _TRUE
        and fields.get("attests-complete-requirement-coverage") == _TRUE
    )
    return reviewer_identity if attests else None
