"""Tests for the parking record's per-leg wording and its derived actions.

The happy path through a real dispatch is bound in
`tests/integration/test_acceptance_parking_record_scenario138.py`, and the write
that carries this record to the ledger is covered beside it in
`test_dispatcher_acceptance_park.py`. What THIS module owns is everything one
verdict's worth of dispatch cannot reach: each named leg's own remedy, the
no-pending-leg park that names the human valve instead, and the pull-request
phrase for a merge that recorded no pull request.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    EFFECTIVE_CRITERIA_LEG,
    EMPTY_MERGED_DIFF_LEG,
    MERGED_DIFF_LEG,
    NEEDS_ATTENTION_VERDICT,
    TELEMETRY_LEG,
    AcceptancePassResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    PARKING_RECORD_TITLE,
    parking_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
    change_classification,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records

_ITEM_ID = "bd-ib-park"
_ASSERTION = "The projection carries the parent field."
_HUMAN_ASSERTION = "The production console renders the banner."
_RUN_ID = "01M3PARKUNIT"
_RECORD_URL = "https://example.test/c/1"


def _result(
    *,
    verdict: str = NEEDS_ATTENTION_VERDICT,
    absent_evidence: tuple[str, ...] = (),
    criteria: tuple[CriterionCheck, ...] = (),
    proof: object = None,
) -> AcceptancePassResult:
    return AcceptancePassResult(
        verdict=verdict,
        merged_diff="diff --git a/x b/x\n",
        diff_reason="merged diff read",
        telemetry_observed=True,
        telemetry_passed=True,
        telemetry_reason="green merged dispatch with PR and merge sha",
        criteria=criteria,
        absent_evidence=absent_evidence,
        classification=change_classification(),
        proof=proof,  # pyright: ignore[reportArgumentType] - ProofLeg | None, built below.
    )


def _criteria(*, modes: tuple[str, ...]) -> EffectiveCriteria:
    assertions = (_ASSERTION, _HUMAN_ASSERTION)[: len(modes)]
    return EffectiveCriteria(
        text="\n".join(f"- {one}" for one in assertions),
        assertions=assertions,
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        proof_modes=modes,
    )


def _record_body(*, verdict: str) -> str:
    return (
        f"Proof of Done — {verdict} — run {_RUN_ID} — 2026-10-04T09:00:00Z\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "\n"
        "Reproduced: yes.\n"
    )


def _proof(*, verdict: str, modes: tuple[str, ...]) -> object:
    records = proof_records(comments=({"url": _RECORD_URL, "body": _record_body(verdict=verdict)},))
    return proof_leg(
        criteria=_criteria(modes=modes),
        records=records,
        run_ids=(_RUN_ID,),
        reason=f"pull request #7 records read for run {_RUN_ID}",
    )


@pytest.mark.parametrize(
    ("leg", "expected_opening"),
    [
        (TELEMETRY_LEG, "The dispatch reported no merged pull request"),
        (EMPTY_MERGED_DIFF_LEG, "The merge changed no files."),
        (MERGED_DIFF_LEG, "The merged diff could not be read."),
        (EFFECTIVE_CRITERIA_LEG, "The item's Definition of Done parses to no gradeable"),
        ("proof of done record for 'x'", "Publish a Proof of Done record whose first line"),
    ],
)
def test_each_absent_leg_carries_its_own_remedy_and_the_re_accept_route(
    leg: str,
    expected_opening: str,
) -> None:
    """One remedy per leg, never one generic "re-run the pass" line.

    The legs fail for unrelated reasons and three of them need a REPAIR first, so
    a shared action would tell an operator to re-run a pass that would reproduce
    the identical park — and under this module's own idempotence rule that re-run
    would not even leave a second record saying so. Each case therefore asserts
    BOTH halves: the leg-specific opening, and that the re-accept invocation is
    named with this item's own id.
    """
    record = parking_record(
        item_id=_ITEM_ID,
        policy="ai-only",
        result=_result(absent_evidence=(leg,)),
        pull_request=7,
    )

    assert [one.name for one in record.pending] == [leg]
    action = record.pending[0].action
    assert action.startswith(expected_opening)
    assert f"reconcile-merged --repo <repo> --item {_ITEM_ID} --invoker <role:name>" in action


def test_a_park_with_no_pending_leg_names_the_human_accept_valve() -> None:
    """Scenario 138 — a parked PASS names "the accept valve" as the mover.

    The clause requires "the action that would move the item" of EVERY park, and
    for an ordinary `ai-then-human` PASS there is no pending leg to carry one: the
    mover is a human. The key line records `pending: nothing`, which is what makes
    this park a DISTINCT record from the same verdict with a leg outstanding.
    """
    record = parking_record(
        item_id=_ITEM_ID,
        policy="ai-then-human",
        result=_result(
            verdict="PASS",
            criteria=(CriterionCheck(text=_ASSERTION, passed=True, reason="graded"),),
        ),
        pull_request=7,
    )

    assert record.key_line == f"{PARKING_RECORD_TITLE} — PASS — pending: nothing"
    assert record.render().splitlines()[-1] == (
        f"- nothing is pending: the human `accept:{_ITEM_ID}` valve moves the item to done,"
        f" and `reject:{_ITEM_ID}:rework` returns it to active."
    )
    assert (
        "- effective criteria: OBSERVED — 1 assertion(s) reached a graded check" in record.render()
    )


def test_an_ungradeable_definition_of_done_is_named_as_the_parse_rather_than_a_count() -> None:
    """The criteria leg says WHAT was absent, not "0 assertions graded".

    A count of zero is the same number a proof-graded item with an unevidenced
    assertion produces off perfectly good criteria, so reporting the leg as a
    count would make an ungradeable Definition of Done and an absent proof record
    read identically — and the remedies are nothing alike.
    """
    record = parking_record(
        item_id=_ITEM_ID,
        policy="ai-only",
        result=_result(absent_evidence=(EFFECTIVE_CRITERIA_LEG,)),
        pull_request=7,
    )

    assert "- effective criteria: NOT OBSERVED — the effective criteria parsed to no" in (
        record.render()
    )


def test_a_pending_human_leg_is_named_even_though_the_pass_graded_it_passing() -> None:
    """The one pending leg that is NEVER in `absent_evidence`.

    The AI pass grades a human-attested assertion PASSING by design — the accept
    valve owns that leg — so it never appears as absent evidence. A record derived
    from the absent set alone would therefore omit the only thing actually holding
    the item, which is why these ride beside it.
    """
    record = parking_record(
        item_id=_ITEM_ID,
        policy="ai-then-human",
        result=_result(
            verdict="PASS",
            proof=_proof(
                verdict="verified",
                modes=(PROOF_MODE_FACTORY_CAPTURED, PROOF_MODE_HUMAN_ATTESTED),
            ),
        ),
        pull_request=None,
    )

    assert [one.name for one in record.pending] == [
        f"human-attested record for {_HUMAN_ASSERTION!r}"
    ]
    # No pull request number was recorded, so the phrase NAMES which pull request
    # is meant rather than rendering a `#None` an operator cannot open.
    assert "the pull request of the merging run" in record.pending[0].action
    assert "Proof of Done — human_attested — <human identity>" in record.pending[0].action
