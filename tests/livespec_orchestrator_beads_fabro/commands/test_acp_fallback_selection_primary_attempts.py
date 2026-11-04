"""Tolerance coverage for the PRIMARY half of the selection-derived reading.

The sibling `test_acp_fallback_selection_warning_tolerances.py` covers the
WARNING half, and the two halves do not share a refusal: a warning needs five
stable identities and a strictly positive position, while an attempt needs
position zero and the primary generation alone — the clearance predicate reads
nothing else off it.

EVERY CASE HERE IS PAIRED WITH ITS NEAR-MISS, because an attempt refused on the
wrong ground is indistinguishable from one refused correctly: a non-primary
position and an unreadable generation both yield no attempt, and a reading that
simply never produced one would satisfy both. The ADMITTED case is therefore
asserted in full — its node, its generation, its start and both verdict fields —
and is what makes each absence a finding rather than a constant.

THE `None` RETURN IS A THIRD ANSWER AND NOT AN EMPTY ONE. An empty outcome map
is evidence that could not be READ, which must not clear a warning; the empty
TUPLE is a selection that joins to no executed node, which is the ordinary
answer for a node the run never reached. The two are asserted apart here, since
`reconcile_runs` treats them identically only by accident of both being falsy
and a reading that collapsed them would retire a standing warning on a failed
read.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_fallback_selection_warnings import (
    selection_primary_attempts,
)

_ITEM = "item"
_RUN = "run"
_NODE = "implement"
_AT = "2026-10-22T09:00:00Z"


def _records(*, choice: object) -> tuple[dict[str, object], ...]:
    return (
        {
            "at": _AT,
            "stage": "acp-node-selection",
            "work_item_id": _ITEM,
            "selections": {_NODE: choice},
        },
    )


def _primary_choice() -> dict[str, object]:
    """One complete selection that stayed at candidate zero."""
    return {
        "selection_identity": "selection-1",
        "selected_index": 0,
        "selected_candidate_key": "primary",
        "selected_availability_key": "availability",
        "primary_generation_digest": "primary-1",
        "full_chain_digest": "chain-1",
    }


def _attempts(*, choice: object, status: str = "succeeded") -> object:
    return selection_primary_attempts(
        records=_records(choice=choice),
        work_item_id=_ITEM,
        run_id=_RUN,
        outcomes={f"{_NODE}@1": {"status": status}},
    )


def test_an_executed_primary_selection_is_one_attempt_the_rule_can_read() -> None:
    """The admitted case, in full: without it every absence below is vacuous."""
    attempts = _attempts(choice=_primary_choice())

    assert attempts is not None
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.node == _NODE
    assert attempt.primary_generation == "primary-1"
    assert attempt.started_at == _AT
    assert attempt.executed is True
    assert attempt.succeeded is True


def test_a_primary_the_run_did_not_succeed_at_is_executed_but_unsuccessful() -> None:
    """Executed and succeeded are separate fields because they refuse separately."""
    attempts = _attempts(choice=_primary_choice(), status="failed")

    assert attempts is not None
    assert [(one.executed, one.succeeded) for one in attempts] == [(True, False)]


@pytest.mark.parametrize("index", [1, True, -1, "0", None])
def test_only_candidate_zero_is_a_primary_attempt(index: object) -> None:
    """A fallback position is the reason a warning exists, never its clearance."""
    assert _attempts(choice={**_primary_choice(), "selected_index": index}) == ()


@pytest.mark.parametrize("generation", [" ", "", None, 1])
def test_an_unreadable_primary_generation_is_no_attempt(generation: object) -> None:
    """The generation is the whole of what the clearance rule matches on."""
    assert _attempts(choice={**_primary_choice(), "primary_generation_digest": generation}) == ()


def test_a_malformed_selection_entry_is_no_attempt() -> None:
    """A node whose selection is not a mapping carries no position to read."""
    assert _attempts(choice="not-a-map") == ()


def test_unreadable_node_outcomes_are_unavailable_and_not_an_empty_attempt_set() -> None:
    """`None` must not read as "this run attempted no primary"."""
    assert (
        selection_primary_attempts(
            records=_records(choice=_primary_choice()),
            work_item_id=_ITEM,
            run_id=_RUN,
            outcomes={},
        )
        is None
    )


def test_a_node_the_run_never_executed_contributes_no_attempt() -> None:
    """An unexecuted preflight selection is not evidence about the primary."""
    assert (
        selection_primary_attempts(
            records=_records(choice=_primary_choice()),
            work_item_id=_ITEM,
            run_id=_RUN,
            outcomes={"review@1": {"status": "succeeded"}},
        )
        == ()
    )
