"""Per-assertion evidence grading shared by proof-record readers."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    HostAssertionGrade,
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

__all__: list[str] = ["assertion_evidence"]

_HOST_LEG = "host-captured record"
_HUMAN_LEG = "human-attested record"
_PENDING_HUMAN_REASON = (
    "pending human attestation; graded by the accept valve, never by the AI pass"
)


def assertion_evidence(
    *,
    text: str,
    proof_mode: str,
    record: ProofRecord | None,
    host: HostAssertionGrade | None,
    attachment_digest: AttachmentDigestReader,
) -> AssertionEvidence:
    """Grade one assertion from its record, host replay, or pending human leg."""
    if proof_mode == PROOF_MODE_HOST_CAPTURED and host is not None:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=_HOST_LEG,
            record_comment=host.record_comment,
            check=CriterionCheck(
                text=text,
                passed=True if host.passed is None else host.passed,
                reason=host.reason,
            ),
        )
    if proof_mode == PROOF_MODE_HUMAN_ATTESTED:
        return AssertionEvidence(
            text=text,
            proof_mode=proof_mode,
            leg=_HUMAN_LEG,
            record_comment=None,
            check=CriterionCheck(text=text, passed=True, reason=_PENDING_HUMAN_REASON),
        )
    if record is None:
        return _unobserved(text=text, proof_mode=proof_mode, record_comment=None)
    reproduced = record.reproduced(assertion=text)
    if reproduced is None:
        return _unobserved(text=text, proof_mode=proof_mode, record_comment=record.url)
    attachment = record.attachment(assertion=text)
    if attachment is not None and not attachment_is_evidence(
        attachment=attachment, fetched=attachment_digest(name=attachment.name)
    ):
        return _unobserved(text=text, proof_mode=proof_mode, record_comment=record.url)
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


def _unobserved(*, text: str, proof_mode: str, record_comment: str | None) -> AssertionEvidence:
    return AssertionEvidence(
        text=text,
        proof_mode=proof_mode,
        leg=PROOF_RECORD_EVIDENCE_LEG,
        record_comment=record_comment,
        check=None,
    )


def _graded_reason(*, record: ProofRecord, reproduced: bool) -> str:
    listing = "reproduced" if reproduced else "not reproduced"
    return (
        f"{PROOF_RECORD_TITLE} {record.verdict} record {record.url}"
        f" lists the assertion as {listing}"
    )
