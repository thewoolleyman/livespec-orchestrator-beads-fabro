"""The whole refusal ladder of an evidenced causal supersession, read purely.

The one admitted path and five of its refusals are bound at the integration tier
by `tests/integration/test_plan_misderived_supersession.py`, which drives
`set_next_action` over the real store. This module covers the arms that tier
cannot REACH, and they are the arms that matter most: each of them is a state in
which a supersession would be ADMITTED if the condition it grades were dropped,
and a ledger a test can build does not reach them.

THE DIRECTION EVERY CASE ARGUES IN. A supersession is the ONE write that may
rename an unmet obligation, so every condition dropped here is a route past the
clause's own refusal — "a new label, repair-child milestone, acknowledgment or
changed-approach claim cannot evade expiry". The refusals are therefore graded on
WHICH condition they report as well as on their existence: a reader told its
carrier is closed, about a supersession that also named the wrong epoch, fixes
the carrier and meets the same refusal again.

THE DEFAULT EVIDENCE NAMES A DERIVATION THAT REALLY DID WRITE THE OBLIGATION
STANDING NOW, which is what keeps each refusal attributable to the one condition
its own case stages. The provenance condition — that the named derivation wrote
the retained obligation — runs ahead of the author and carrier conditions, so a
default recording some other result would report that one for every case in the
module and the conditions below would never be reached.

AND THE ONE PAIR THAT MUST NOT BE COLLAPSED. A carrier closed BEFORE the
derivation and a carrier closed SINCE are both "closed now", and the clause gives
them different reasons: the first means the derived step could legitimately have
been taken, so nothing was misderived; the second means the replacement result is
already satisfied, which no cause may trade an obligation for. One refusal
serving both sends half its readers to the wrong question.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
    CAUSE_DISPOSED,
    CAUSE_MISDERIVED,
    CAUSE_SUBSUMED,
    DERIVATION_ACTORS,
    SUPERSESSION_CAUSES,
    CarrierEvidence,
    CausalSupersession,
    DerivingTransition,
    SupersessionEvidence,
    SupersessionRefusal,
    validate_causal_supersession,
)

_EPIC = "bd-ib-plan"
_CARRIER = "cr-open"
_IDENTITY = f"repo item_comment {_EPIC} marker 'Plan Proof of Done'"
_EPOCH = 3
_DERIVED_AT = "2026-10-22T07:00:00Z"
_BEFORE = "2026-10-21T07:00:00Z"
_AFTER = "2026-10-22T09:00:00Z"
# The obligation the identity above renders, so the DEFAULT evidence names a
# derivation that really did write what stands now: every refusal below is then
# about the one condition its own case stages.
_OBLIGATION: dict[str, object] = {
    "repo": "repo",
    "item_comment": {"item_id": _EPIC, "marker": "Plan Proof of Done"},
}
_REPLACEMENT: dict[str, object] = {
    "repo": "carrier-repo",
    "item_status": {"item_id": _CARRIER, "status": "closed"},
}


def _supersession(**overrides: object) -> CausalSupersession:
    fields: dict[str, object] = {
        "superseded_result_identity": _IDENTITY,
        "previous_epoch": _EPOCH,
        "cause": CAUSE_MISDERIVED,
        "deriving_operation_id": "op-derived",
        "open_carrier_id": _CARRIER,
        "writer": "plan-session",
    }
    fields.update(overrides)
    return CausalSupersession(**fields)  # pyright: ignore[reportArgumentType]


def _deriving(*, author: str = DERIVATION_ACTORS[0]) -> DerivingTransition:
    """A derivation that really did write the obligation, and was retained since.

    Both provenance fields are supplied so every refusal below is attributable to
    the one condition its own case stages; the grade itself is covered beside it,
    in `test_plan_supersession_provenance.py`.
    """
    return DerivingTransition(
        author=author, recorded_at=_DERIVED_AT, required_result=_OBLIGATION, later_results=()
    )


def _evidence(
    *,
    author: str = DERIVATION_ACTORS[0],
    deriving: bool = True,
    carrier: CarrierEvidence | None = None,
    plan_level: bool = True,
) -> SupersessionEvidence:
    return SupersessionEvidence(
        deriving=_deriving(author=author) if deriving else None,
        carrier=carrier
        if carrier is not None
        else CarrierEvidence(mapped=True, status="ready", closed_at=None),
        plan_level=plan_level,
    )


def _refusal(**kwargs: object) -> SupersessionRefusal:
    verdict = validate_causal_supersession(**kwargs)  # pyright: ignore[reportArgumentType]
    assert isinstance(verdict, SupersessionRefusal), verdict
    return verdict


def test_an_evidenced_misderived_supersession_of_an_open_carrier_is_admitted() -> None:
    """The positive control for every refusal below.

    Without it, a validator refusing unconditionally satisfies the whole module
    while making the only sanctioned route past the rename refusal unreachable —
    which is the state the measured plan epic was locked in.
    """
    assert (
        validate_causal_supersession(
            supersession=_supersession(),
            evidence=_evidence(),
            prior_identity=_IDENTITY,
            current_epoch=_EPOCH,
            replacement=_REPLACEMENT,
        )
        is None
    )


def test_the_ratified_cause_set_is_closed_and_holds_the_three_the_clause_names() -> None:
    """The grammar is the ratified one, not whatever this build can verify.

    Spelled as an assertion rather than left to the module, because the SET and
    the VERIFIABLE SUBSET are deliberately different: a later implementer reading
    only the refusal would infer a one-member grammar and widen it by inventing
    names.
    """
    assert SUPERSESSION_CAUSES == (CAUSE_MISDERIVED, CAUSE_DISPOSED, CAUSE_SUBSUMED)


@pytest.mark.parametrize("cause", [CAUSE_DISPOSED, CAUSE_SUBSUMED])
def test_a_ratified_cause_this_build_cannot_verify_is_refused_naming_itself(cause: str) -> None:
    """A cause whose evidence does not verify is refused, as the clause requires.

    Fail-closed in the only direction available: before the surface existed,
    all three were refused, so refusing the two whose evidence this build takes
    no reading for changes nothing — while admitting them would admit a rename
    on an unchecked claim.
    """
    verdict = _refusal(
        supersession=_supersession(cause=cause),
        evidence=_evidence(),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert cause in verdict.detail
    assert CAUSE_MISDERIVED in verdict.detail


def test_a_supersession_naming_another_obligation_is_refused() -> None:
    """The identity must be the one the CHAIN holds, not one the caller chose."""
    verdict = _refusal(
        supersession=_supersession(superseded_result_identity="repo item_status other closed"),
        evidence=_evidence(),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert _IDENTITY in verdict.detail


def test_a_supersession_naming_another_epoch_is_refused() -> None:
    """A stale epoch names a transition this chain has already moved past."""
    verdict = _refusal(
        supersession=_supersession(previous_epoch=_EPOCH - 1),
        evidence=_evidence(),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert str(_EPOCH) in verdict.detail


def test_evidence_that_could_not_be_read_at_all_is_refused() -> None:
    """A reading nobody took establishes nothing, so it cannot admit a rename."""
    verdict = _refusal(
        supersession=_supersession(),
        evidence=None,
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert "evidence" in verdict.detail


def test_an_obligation_whose_target_is_not_the_plan_epic_is_not_plan_level() -> None:
    """The plan-level arm is the only `misderived` arm this build verifies.

    The cause's other arm — an `impl` step whose target already carried a
    `factory-safety` label — takes a different reading entirely, so an
    obligation that is not plan-level is refused rather than graded against
    carrier evidence that says nothing about it.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=_evidence(plan_level=False),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert "plan epic" in verdict.detail


def test_a_deriving_operation_that_resolves_to_no_transition_is_refused() -> None:
    """The named identity must resolve to that epoch's recorded transition."""
    verdict = _refusal(
        supersession=_supersession(),
        evidence=_evidence(deriving=False),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert "op-derived" in verdict.detail


def test_an_obligation_no_derivation_wrote_is_refused_naming_its_writer() -> None:
    """The cause is accepted only for the two reserved derivation actors.

    The evidence names a derivation that DID write the obligation standing now,
    so the refusal is attributable to the author alone: the provenance condition
    runs first, and a case staging both would report that one instead.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=_evidence(author="plan-session"),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert "plan-session" in verdict.detail


@pytest.mark.parametrize("actor", DERIVATION_ACTORS)
def test_either_reserved_derivation_actor_satisfies_the_derivation_condition(actor: str) -> None:
    """Both actors are admitted, so the refusal above is about the WRITER.

    The clause names `plan-resume` and `plan-archive` alike, and a build
    recognising only one of them refuses every supersession of an obligation the
    archive leg derived — which is a lock no surface would attribute to this
    condition.
    """
    assert (
        validate_causal_supersession(
            supersession=_supersession(),
            evidence=_evidence(author=actor),
            prior_identity=_IDENTITY,
            current_epoch=_EPOCH,
            replacement=_REPLACEMENT,
        )
        is None
    )


@pytest.mark.parametrize(
    ("label", "carrier"),
    [
        ("a carrier reading that could not be taken", None),
        (
            "a carrier the latest carrier-map event does not name",
            CarrierEvidence(mapped=False, status="ready", closed_at=None),
        ),
    ],
)
def test_carrier_evidence_about_nothing_this_plan_asserted_is_refused(
    label: str, carrier: CarrierEvidence | None
) -> None:
    """An unmapped carrier is evidence about nothing the plan's own map claimed.

    The two shapes are kept together because they refuse identically and for one
    reason: neither establishes that a carrier of one of THIS plan's assertions
    was open, which is the whole of what the cause rests on.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=SupersessionEvidence(deriving=_deriving(), carrier=carrier, plan_level=True),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert _CARRIER in verdict.detail, label
    assert "carrier-map" in verdict.detail, label


@pytest.mark.parametrize(
    ("label", "closed_at", "expected"),
    [
        ("closed before the derivation", _BEFORE, "already closed"),
        ("closed at the exact derivation instant", _DERIVED_AT, "already closed"),
        ("closed at an instant the ledger does not record", None, "already closed"),
        ("closed at an instant that will not parse", "not-an-instant", "already closed"),
        ("closed at an instant carrying no timezone", "2026-10-22T09:00:00", "already closed"),
        ("closed at an instant on another offset", "2026-10-22T11:00:00+02:00", "already closed"),
        ("closed after the derivation", _AFTER, "closed now"),
    ],
)
def test_a_closed_carrier_is_refused_and_the_refusal_names_which_reading_closed_it(
    label: str, closed_at: str | None, expected: str
) -> None:
    """The two closed readings have different remedies and different reasons.

    A carrier closed at or before the derivation means the step could
    legitimately have been taken; one closed since means the replacement is
    already satisfied. The three UNDATABLE shapes route to the FIRST, which is
    the conservative direction: the other arm ADMITS a supersession, and a
    supersession cannot be undone.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=_evidence(
            carrier=CarrierEvidence(mapped=True, status="closed", closed_at=closed_at)
        ),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert expected in verdict.detail, label


def test_an_undatable_derivation_instant_also_refuses_a_closed_carrier() -> None:
    """The unreadable instant may be on EITHER side of the comparison.

    Its own control is the passing case above, where the same closure instant
    sits beside a readable derivation instant and reports the other refusal: a
    build reading only the carrier's half would answer `closed now` here.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=SupersessionEvidence(
            deriving=DerivingTransition(
                author=DERIVATION_ACTORS[0],
                recorded_at="whenever",
                required_result=_OBLIGATION,
                later_results=(),
            ),
            carrier=CarrierEvidence(mapped=True, status="closed", closed_at=_AFTER),
            plan_level=True,
        ),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=_REPLACEMENT,
    )

    assert "already closed" in verdict.detail


@pytest.mark.parametrize(
    ("label", "replacement"),
    [
        ("a reference the typed parse refuses", {"shell": "test -f done"}),
        (
            "another target kind entirely",
            {"repo": "repo", "item_comment": {"item_id": _CARRIER, "marker": "done"}},
        ),
        (
            "another item's closure",
            {"repo": "repo", "item_status": {"item_id": "cr-other", "status": "closed"}},
        ),
        (
            "the same carrier at another status",
            {"repo": "repo", "item_status": {"item_id": _CARRIER, "status": "ready"}},
        ),
    ],
)
def test_a_replacement_that_is_not_the_named_carriers_closure_is_refused(
    label: str, replacement: dict[str, object]
) -> None:
    """The evidence is a carrier, so it is evidence for waiting on that carrier.

    A replacement free to name anything else makes the carrier a verified
    footnote attached to an unrelated rename, which is the shape the whole cause
    exists to refuse.
    """
    verdict = _refusal(
        supersession=_supersession(),
        evidence=_evidence(),
        prior_identity=_IDENTITY,
        current_epoch=_EPOCH,
        replacement=replacement,
    )

    assert _CARRIER in verdict.detail, label
