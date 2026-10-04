"""Carrier-line grammar cases a well-formed carrier map never reaches.

`test_plan_carrier_map.py` drives the clause's own behaviour through the real
`record_scope_event`. This module covers what `_mapped_ordinals` does with a
line that does NOT match the grammar, which is a deliberate tolerance rather
than an accident: a malformed line contributes no ordinal, so the assertion it
was meant to map reports as UNMAPPED and the refusal names that assertion. A
parse error would instead name the syntax and leave the author to work out which
assertion went missing.

The same `_edges` split as `test_plan_archive_review_edges.py`, for the same
reason: these inputs are unreachable from the front-end path the sibling drives.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    PlanCarrierMapRefusedError,
    guard_carrier_map,
)

_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The released build answers on the operator host.\n"
    "- The operator drives one loop and sees the agent respond.\n"
)


@pytest.mark.parametrize(
    ("label", "line"),
    [
        ("no ordinal separator at all", "bd-ib-child"),
        ("a non-numeric ordinal", "first: bd-ib-child"),
        ("an empty ordinal", ": bd-ib-child"),
    ],
)
def test_a_malformed_carrier_line_maps_nothing_and_the_assertion_reports_unmapped(
    label: str, line: str
) -> None:
    with pytest.raises(PlanCarrierMapRefusedError) as refusal:
        guard_carrier_map(
            epic_id="bd-ib-epic",
            description=_SECTION,
            carriers=(line, "2: plan-level proof"),
        )

    # Assertion 1 is the one the malformed line was reaching for, so it — and
    # only it — is named. Assertion 2's well-formed line still maps.
    message = str(refusal.value)
    assert "The released build answers on the operator host." in message, label
    assert "The operator drives one loop and sees the agent respond." not in message, label


def test_the_list_marker_is_tolerated_on_a_carrier_line() -> None:
    """A caller that pastes the rendered block back in is not punished for it.

    The rendered block writes each line as `- <ordinal>: <target>`, so the
    marker is what a copy-paste carries. Stripping it here means the argument
    form and the rendered form are both accepted.
    """
    guard_carrier_map(
        epic_id="bd-ib-epic",
        description=_SECTION,
        carriers=("- 1: bd-ib-child", "2: plan-level proof"),
    )
