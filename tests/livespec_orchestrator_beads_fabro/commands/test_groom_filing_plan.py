"""The filing-plan grammar: what it accepts, and every shape it refuses.

The plan is the ONE artifact that crosses from a factory sandbox into a
host-side ledger write with no human between, and the ledger has no undo. So
this module's job is not to be permissive: a plan the parser cannot reproduce
EXACTLY is a cut the reviewer approved in a shape this code cannot rebuild, and
filing a guessed-at version of it would file something no human ever saw.

EVERY REFUSAL IS ASSERTED SEPARATELY because each one names a different defect
an operator has to go and fix, and a single "raises GroomDraftError" case would
pass while the parser blamed the wrong field.

THE DISCRIMINATOR IS ASSERTED IN BOTH DIRECTIONS. `is_groom_filing_plan` is
what tells an apply phase's plan from a propose phase's draft on the one
channel they share, and both errors are expensive: a draft mistaken for a plan
would be FILED, and a plan mistaken for a draft would land as a fresh draft
comment after the approval and revoke the consent it was published under.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._groom_filing_plan import (
    GROOM_PLAN_MARKER,
    is_groom_filing_plan,
    parse_groom_filing_plan,
)
from livespec_orchestrator_beads_fabro.errors import GroomDraftError

_HEADER = f"{GROOM_PLAN_MARKER} | approver=thewoolleyman | route=resolve-blocked ready valve"
_SLICE_FIELDS: dict[str, str] = {
    "slice": "Move the filing host-side",
    "tier": "factory",
    "repo": "orchestrator",
    "acceptance": "The Dispatcher files the cut.",
    "blockers": "none",
    "spec": "no",
    "scope": "Read the plan off the terminated run.",
}
_DRAFT = "slice=A | layer=1 | tier=factory | repo=orchestrator | acceptance=It lands."


def _slice(**overrides: str) -> str:
    """One slice record, so a case names the field it is breaking rather than editing prose."""
    fields = {**_SLICE_FIELDS, **overrides}
    return " | ".join(f"{key}={value}" for key, value in fields.items())


_SLICE = _slice()


def test_a_well_formed_plan_parses_into_its_approval_and_its_slices() -> None:
    plan = parse_groom_filing_plan(text=f"{_HEADER} ;; {_SLICE}")

    assert plan.approver == "thewoolleyman"
    assert plan.route == "resolve-blocked ready valve"
    assert len(plan.slices) == 1
    assert plan.slices[0].title == "Move the filing host-side"
    assert plan.slices[0].description == "Read the plan off the terminated run."
    assert plan.slices[0].depends_on == ()
    assert plan.slices[0].is_spec_change is False


def test_blocker_handles_are_split_into_earlier_slice_titles() -> None:
    """The layering rides as a comma-separated list of EARLIER slice titles."""
    plan = parse_groom_filing_plan(text=f"{_HEADER} ;; {_slice(blockers='Slice A, Slice B')}")

    assert plan.slices[0].depends_on == ("Slice A", "Slice B")


def test_a_spec_change_slice_is_marked_rather_than_dropped() -> None:
    """`spec=yes` routes to propose-change; the filing seam is what withholds it."""
    plan = parse_groom_filing_plan(text=f"{_HEADER} ;; {_slice(spec='yes')}")

    assert plan.slices[0].is_spec_change is True


def test_a_plan_line_is_told_apart_from_a_draft_line_in_both_directions() -> None:
    assert is_groom_filing_plan(text=f"{_HEADER} ;; {_SLICE}") is True
    assert is_groom_filing_plan(text=_DRAFT) is False


def test_a_line_that_does_not_open_with_the_marker_is_refused_by_the_parse() -> None:
    """Reaching the parse with a draft means the discrimination went wrong.

    Refused loudly rather than returned as `None`, because a silent nothing
    here reads exactly like a plan that legitimately named no slices.
    """
    with pytest.raises(GroomDraftError, match=GROOM_PLAN_MARKER):
        _ = parse_groom_filing_plan(text=f"{_DRAFT} ;; {_SLICE}")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (f"{GROOM_PLAN_MARKER} | route=the valve", "approver"),
        (f"{GROOM_PLAN_MARKER} | approver=thewoolleyman", "approver"),
    ],
)
def test_a_header_naming_no_approver_or_no_route_is_refused(header: str, expected: str) -> None:
    """Both halves of the approval record are required before anything is filed.

    The filing seam refuses a call carrying neither, so catching it here only
    means the refusal names the plan rather than the seam — but an invented
    value would attribute a maintainer-tier mutation to someone who never
    approved it, and that is what neither layer may allow.
    """
    with pytest.raises(GroomDraftError, match=expected):
        _ = parse_groom_filing_plan(text=f"{header} ;; {_SLICE}")


def test_a_plan_naming_no_slice_is_refused() -> None:
    with pytest.raises(GroomDraftError, match="no slice"):
        _ = parse_groom_filing_plan(text=_HEADER)


def test_a_field_carrying_no_assignment_is_refused_rather_than_skipped() -> None:
    """A bare word between the separators is a field the author meant to write."""
    with pytest.raises(GroomDraftError, match="carries no"):
        _ = parse_groom_filing_plan(text=f"{_HEADER} | approver-is-missing ;; {_SLICE}")


def test_an_empty_field_between_separators_is_tolerated() -> None:
    """A doubled separator carries no claim, so it is passed over rather than refused.

    The distinction from the case above is the whole point: a BARE WORD is
    something the author wrote and meant, while a doubled separator is a
    typing slip that asserts nothing. Refusing the slip would send an
    otherwise-correct approved cut back through a review round for whitespace.
    """
    plan = parse_groom_filing_plan(text=f"{_HEADER} |  ;; {_SLICE}")

    assert plan.approver == "thewoolleyman"
    assert len(plan.slices) == 1


def test_a_slice_record_naming_no_title_is_refused() -> None:
    with pytest.raises(GroomDraftError, match="no slice title"):
        _ = parse_groom_filing_plan(text=f"{_HEADER} ;; {_slice(slice='')}")


def test_a_slice_naming_an_unknown_tier_is_refused() -> None:
    """The tier decides whether a slice is dispatchable at all, so it is closed."""
    with pytest.raises(GroomDraftError, match="tier"):
        _ = parse_groom_filing_plan(text=f"{_HEADER} ;; {_slice(tier='maybe')}")


@pytest.mark.parametrize("field", ["repo", "acceptance", "scope"])
def test_a_slice_missing_a_field_the_filing_seam_gates_on_is_refused(field: str) -> None:
    """An empty acceptance would file a slice later refused at dispatch.

    That failure surfaces long after the cut was approved and reads as a defect
    in the dispatched slice rather than in the plan that filed it, which is why
    the emptiness is caught here.
    """
    with pytest.raises(GroomDraftError, match=f"empty {field}"):
        _ = parse_groom_filing_plan(text=f"{_HEADER} ;; {_slice(**{field: ''})}")
