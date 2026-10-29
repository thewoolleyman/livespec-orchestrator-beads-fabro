"""Grading one `factory_captured` assertion from a published Proof of Done record.

Split out of `_dispatcher_proof_evidence` along the cohesion seam between WHICH
mode an assertion carries and HOW a factory assertion is graded once a record is
chosen: the first routes host and human assertions to their own legs, this one owns
the three outcomes a factory record can have for an assertion — absent, unreadable
or unfetchable (UNEVIDENCED), and graded.

A `captured` record carries no per-assertion `Reproduced:` verdict and so grades
nothing, but when it is the only factory record the merge has, it is the record the
pass must be able to NAME. It rides on the unevidenced result's `record_comment`.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment_verify import (
    AttachmentDigestReader,
    attachment_is_evidence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
    AssertionEvidence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    ProofRecord,
)

__all__: list[str] = [
    "factory_assertion_evidence",
]


def factory_assertion_evidence(
    *,
    text: str,
    proof_mode: str,
    record: ProofRecord | None,
    captured: ProofRecord | None,
    attachment_digest: AttachmentDigestReader,
) -> AssertionEvidence:
    """Grade one factory assertion off the merging dispatch's `verified` record."""
    if record is None:
        # A `captured` record grades nothing, so the assertion stays UNEVIDENCED; it
        # is named here so the journal and the parking record can say which record
        # the pull request holds instead of reporting the evidence as absent.
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=PROOF_RECORD_EVIDENCE_LEG,
            record_comment=None if captured is None else captured.url,
            check=None,
        )
    reproduced = record.reproduced(assertion=text)
    if reproduced is None:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=PROOF_RECORD_EVIDENCE_LEG,
            record_comment=record.url,
            check=None,
        )
    # An assertion whose proof travels as an ASSET is graded on the asset, not on
    # the record's account of it: the record holds a pointer rather than the
    # evidence, so a verdict read from the record alone would rest on the
    # publisher's say-so. A missing or mismatched asset is ABSENT evidence — the
    # same unevidenced shape as an unreadable verdict — and never a FAIL, because
    # an unfetchable proof says nothing about whether the behaviour holds and a
    # FAIL would consume a rework attempt the clause forbids spending.
    attachment = record.attachment(assertion=text)
    if attachment is not None and not attachment_is_evidence(
        attachment=attachment, fetched=attachment_digest(name=attachment.name)
    ):
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=PROOF_RECORD_EVIDENCE_LEG,
            record_comment=record.url,
            check=None,
        )
    return AssertionEvidence(
        text=text,
        proof_mode=proof_mode,
        leg=PROOF_RECORD_EVIDENCE_LEG,
        record_comment=record.url,
        check=CriterionCheck(
            text=text,
            passed=reproduced,
            reason=_graded_reason(record=record, reproduced=reproduced),
        ),
    )


def _graded_reason(*, record: ProofRecord, reproduced: bool) -> str:
    listing = "reproduced" if reproduced else "not reproduced"
    return (
        f"{PROOF_RECORD_TITLE} {record.verdict} record {record.url}"
        f" lists the assertion as {listing}"
    )
