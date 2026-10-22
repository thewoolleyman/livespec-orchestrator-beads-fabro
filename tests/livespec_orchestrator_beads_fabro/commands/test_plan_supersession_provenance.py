"""Whether the derivation a supersession names wrote the obligation standing now.

The two states a healthy ledger produces are bound at the integration tier by
`tests/integration/test_plan_misderived_supersession_retained.py`, which drives
`set_next_action` over the real store: a derivation that recorded another
obligation, and one whose result a later transition changed. This module covers
the states that tier cannot STAGE, because a chain whose transitions are
committed through the production writer records a typed reference on every one of
them — while a live ledger holds whatever a build of any age wrote.

EVERY CASE HERE ARGUES IN THE SAME DIRECTION. The grade's whole job is to stop an
operation identity that resolves at its OWN epoch from selecting some other
transition of the plan, so each condition dropped is a route to a supersession
that reads as fully evidenced while naming a derivation with nothing to do with
the result it replaces. The two no-objection cases are the positive controls:
without them a grade that objected unconditionally would satisfy every refusal
here while making the sanctioned route past the rename refusal unreachable.

THE REFUSALS ARE GRADED ON WHICH CONDITION THEY REPORT, and the two conditions'
words are asserted MUTUALLY ABSENT. A reader told its derivation recorded another
obligation, about a chain that in fact changed the result and changed it back,
fixes the identity and meets the same refusal again.

AND NO CASE ASSERTS THE RAW RECORDED VALUE IS RENDERED BACK. It is untrusted
ledger content and the grade deliberately names an unplaceable one by the word it
reserves for that absence, which is asserted against the module's own constant
rather than transcribed.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference
from livespec_orchestrator_beads_fabro.commands._plan_supersession_provenance import (
    UNREADABLE_REFERENCE,
    provenance_detail,
)

_EPIC = "bd-ib-plan"
_OPERATION = "op-derived"
_OBLIGATION: dict[str, object] = {
    "repo": "repo",
    "item_comment": {"item_id": _EPIC, "marker": "Plan Proof of Done"},
}
_OTHER: dict[str, object] = {
    "repo": "repo",
    "item_comment": {"item_id": _EPIC, "marker": "plan-completeness-review-evidence"},
}
_RECORDED_ANOTHER = "recorded the required result"
_CHANGED_AFTER = "changed the required result"


def _identity(*, required_result: dict[str, object]) -> str:
    """The canonical result identity, ASKED OF the production reference parse.

    Not transcribed: a literal written here would keep passing after the
    rendering had changed, which is a green that is no longer about anything.
    """
    parsed = parse_result_reference(value=required_result)
    assert isinstance(parsed, ResultReference), parsed
    return parsed.identity


def _detail(*, recorded_result: object, later_results: tuple[object, ...]) -> str:
    detail = provenance_detail(
        operation_id=_OPERATION,
        recorded_result=recorded_result,
        later_results=later_results,
        prior_identity=_identity(required_result=_OBLIGATION),
    )
    assert detail is not None
    return detail


@pytest.mark.parametrize(
    ("label", "later_results"),
    [
        ("a derivation nothing followed", ()),
        ("every later transition retaining the result", (_OBLIGATION, _OBLIGATION)),
    ],
)
def test_a_derivation_that_wrote_and_kept_the_obligation_draws_no_objection(
    label: str, later_results: tuple[object, ...]
) -> None:
    """The positive controls for every refusal below.

    The two shapes are both needed: the empty one exercises no comparison at all,
    while the populated one is the only case in which the retention loop RUNS and
    finds nothing to object to — a grade that refused on any later transition
    would pass the empty case and lock every plan whose obligation was ever
    retained, which is the measured incident this grade sits inside.
    """
    objection = provenance_detail(
        operation_id=_OPERATION,
        recorded_result=_OBLIGATION,
        later_results=later_results,
        prior_identity=_identity(required_result=_OBLIGATION),
    )

    assert objection is None, label


@pytest.mark.parametrize(
    ("label", "recorded_result"),
    [
        ("a recorded result nothing can parse as a typed reference", {"shell": "test -f done"}),
        ("a transition that recorded no result at all", None),
    ],
)
def test_a_derivation_whose_recorded_result_cannot_be_placed_is_refused(
    label: str, recorded_result: object
) -> None:
    """A recorded value with no canonical identity wrote no obligation.

    The comparison is between CANONICAL IDENTITIES, so a value that parses to
    none compares unequal to every obligation — the fail-closed answer, since a
    transition whose recorded result this reader cannot place cannot be shown to
    have written anything.
    """
    detail = _detail(recorded_result=recorded_result, later_results=())

    assert UNREADABLE_REFERENCE in detail, label
    assert _identity(required_result=_OBLIGATION) in detail, label
    assert _RECORDED_ANOTHER in detail, label
    assert _CHANGED_AFTER not in detail, label


def test_a_derivation_that_recorded_another_obligation_is_refused_naming_both() -> None:
    """The refusal names what the derivation wrote AND what it is not."""
    detail = _detail(recorded_result=_OTHER, later_results=())

    assert _RECORDED_ANOTHER in detail
    assert _CHANGED_AFTER not in detail
    assert _identity(required_result=_OTHER) in detail
    assert _identity(required_result=_OBLIGATION) in detail


@pytest.mark.parametrize(
    ("label", "later_results", "changed_to"),
    [
        (
            "a later transition that changed the result and never restored it",
            (_OTHER,),
            _identity(required_result=_OTHER),
        ),
        (
            "a later transition whose own recorded result cannot be placed",
            (None,),
            UNREADABLE_REFERENCE,
        ),
        (
            "the FIRST of several later transitions that changed it",
            (_OTHER, _OBLIGATION),
            _identity(required_result=_OTHER),
        ),
    ],
)
def test_a_later_transition_that_did_not_retain_the_result_is_refused(
    label: str, later_results: tuple[object, ...], changed_to: str
) -> None:
    """The retention half, reported as what the later transition changed it to.

    The third row is the one worth keeping: the derivation recorded the result,
    the chain changed it and changed it back, so the obligation standing now was
    written by the restoring transition — and a grade that compared only the
    LATEST later result would read that chain as having retained it throughout.
    """
    detail = _detail(recorded_result=_OBLIGATION, later_results=later_results)

    assert _CHANGED_AFTER in detail, label
    assert _RECORDED_ANOTHER not in detail, label
    assert changed_to in detail, label
    assert _identity(required_result=_OBLIGATION) in detail, label


def test_every_refusal_names_the_deriving_operation_it_is_about() -> None:
    """Both refusals carry the operation identity, which is what a reader fixes.

    Asserted across both arms in one case, because an operation id the refusals
    omitted would leave a reader of a multi-derivation plan with no way to tell
    which of its derivations the grade rejected.
    """
    assert _OPERATION in _detail(recorded_result=_OTHER, later_results=())
    assert _OPERATION in _detail(recorded_result=_OBLIGATION, later_results=(_OTHER,))
