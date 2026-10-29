"""Tests for the parking record of a pull request holding only a `captured` record.

A `captured` record carries no per-assertion `Reproduced:` verdict, so it grades
no `factory_captured` assertion: each one is UNOBSERVED and the pass parks on
NEEDS_ATTENTION. The parking record must then name the record the pull request
does hold and the one action that supersedes it, the proof-only resume arm,
rather than telling the operator to publish a record they already published.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    NEEDS_ATTENTION_VERDICT,
    AcceptancePassResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    parking_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
    change_classification,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import ProofLeg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records

_ITEM_ID = "bd-ib-captured"
_ASSERTION = "The projection carries the parent field."
_RUN_ID = "d547aa765bb3427cb43e70ebc9fd54a6"
_CAPTURED_URL = "https://example.test/pull/7#issuecomment-1"


def _leg(*, run_id: str) -> ProofLeg:
    body = f"Proof of Done — captured — run {run_id} — 2026-10-27T00:46:00Z\n\nCaptured.\n"
    return proof_leg(
        criteria=EffectiveCriteria(
            text=f"- {_ASSERTION}",
            assertions=(_ASSERTION,),
            source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
            proof_modes=(PROOF_MODE_FACTORY_CAPTURED,),
        ),
        records=proof_records(comments=({"url": _CAPTURED_URL, "body": body},)),
        run_ids=(_RUN_ID,),
        reason="pull request #7 records read",
    )


def _park(*, proof: ProofLeg) -> str:
    result = AcceptancePassResult(
        verdict=NEEDS_ATTENTION_VERDICT,
        merged_diff="diff --git a/x b/x\n",
        diff_reason="merged diff read",
        telemetry_observed=True,
        telemetry_passed=True,
        telemetry_reason="green merged dispatch with PR and merge sha",
        criteria=proof.checks,
        absent_evidence=proof.absent_evidence,
        classification=change_classification(),
        proof=proof,
    )
    return parking_record(
        item_id=_ITEM_ID, policy="ai-then-human", result=result, pull_request=7
    ).render()


def test_a_captured_only_pull_request_is_reported_unobserved_naming_the_record_and_the_arm() -> (
    None
):
    proof = _leg(run_id=_RUN_ID)

    rendered = _park(proof=proof)

    assert [one.record_comment for one in proof.assertions] == [_CAPTURED_URL]
    assert "UNOBSERVED" in rendered
    assert _CAPTURED_URL in rendered
    assert "proof-only resume arm" in rendered
    assert f"resume --item {_ITEM_ID}" in rendered
    assert "Publish a Proof of Done record" not in rendered


def test_a_captured_record_of_another_dispatch_is_not_named() -> None:
    proof = _leg(run_id="ffffffffffffffffffffffffffffffff")

    rendered = _park(proof=proof)

    assert [one.record_comment for one in proof.assertions] == [None]
    assert _CAPTURED_URL not in rendered
    assert "Publish a Proof of Done record" in rendered
