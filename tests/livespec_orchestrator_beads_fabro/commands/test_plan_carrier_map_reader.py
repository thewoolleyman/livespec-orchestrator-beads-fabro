"""Reading the carriers back OFF a recorded carrier-map event.

`test_plan_carrier_map.py` drives the WRITE through the real
`record_scope_event`, and `test_plan_carrier_map_edges.py` covers the write's
own grammar tolerance. This module is the read half — `last_carrier_map_carriers`
— and it is a separate concern rather than a continuation of either: the write
is handed a carriers TUPLE and never parses one, so every shape below is a shape
the write path cannot produce or reach.

THE `plan-level proof` CASES SIT HERE RATHER THAN AT THE GATE, because the
carve-out is at the parse: the clause reserves that literal for an assertion no
child carries, so the entry records the ABSENCE of a work-item carrier. Its
behavioural half is bound at the integration tier by
`tests/integration/test_plan_resume_plan_level_proof_carrier.py`; what these
cases pin is that the literal is dropped WITHOUT dropping the work-item carrier
beside it — including when the two share one line, which is the shape a reader
that stopped at the literal would get wrong while passing the per-line case.

WHY THE CASES ARE MOSTLY ABOUT WHAT IS *NOT* A CARRIER. A scope-event body is
made of list lines from its first section onward — every event opens with
`Requirement carriers:` and `Explicit deferrals:`, each carrying bullets of
maintainer prose — so the expensive failure for this reader is not missing a
carrier but inventing one. A reader that collected every `- ` line of the body
would hand the resume a sentence of requirement prose as a work-item id, and the
resume would then wait on it: an id nothing resolves, which is indistinguishable
at the pointer from a carrier in an unconfigured tenant.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    last_carrier_map_carriers,
)

_BODY = (
    "plan-scope-event\n"
    "author: plan-session\n"
    "timestamp: 2026-10-22T07:00:00Z\n"
    "\n"
    "Requirement carriers:\n"
    "- the released build answers on the operator host\n"
    "\n"
    "Explicit deferrals:\n"
    "- the console lane\n"
    "\n"
    "carriers:\n"
)


def _event(*, carrier_lines: tuple[str, ...]) -> dict[str, object]:
    return {"text": _BODY + "\n".join(f"- {one}" for one in carrier_lines)}


def test_no_carrier_map_event_names_no_carriers() -> None:
    """A plan whose timeline carries only rulings has no map to read.

    The discriminator is the `carriers:` LINE, and every scope-event body ends
    its first section header in `carriers:` — so a substring reader would report
    this ruling's own requirement prose as the map.
    """
    assert last_carrier_map_carriers(comments=[{"text": _BODY.replace("carriers:\n", "")}]) == ()


def test_a_comment_carrying_no_readable_text_does_not_displace_the_map() -> None:
    """A later comment with no `text` is not a carrier-map event at all.

    `omitempty`-sparse records omit a key rather than carrying an empty one, so
    a comment with no `text` is a shape the ledger genuinely produces. Treating
    it as the latest map event would answer with no carriers at all for a plan
    whose map is perfectly readable one comment earlier.
    """
    comments = [_event(carrier_lines=("1: cr-one",)), {"created_at": "later"}]

    assert last_carrier_map_carriers(comments=comments) == ("cr-one",)


def test_the_latest_map_event_governs_and_earlier_ones_are_not_unioned() -> None:
    """A carrier a later event dropped is no longer a carrier of this plan."""
    comments = [_event(carrier_lines=("1: cr-first",)), _event(carrier_lines=("1: cr-second",))]

    assert last_carrier_map_carriers(comments=comments) == ("cr-second",)


@pytest.mark.parametrize(
    ("label", "carrier_lines", "expected"),
    [
        ("one carrier per assertion", ("1: cr-one", "2: cr-two"), ("cr-one", "cr-two")),
        ("several carriers on one line", ("1: cr-one, cr-two",), ("cr-one", "cr-two")),
        (
            "one carrier carrying two assertions, collapsed on first appearance",
            ("1: cr-one", "2: cr-one"),
            ("cr-one",),
        ),
        ("a line naming no ordinal maps and names nothing", ("cr-one",), ()),
        (
            "a plan-level proof entry names no work-item carrier",
            ("1: cr-one", "2: plan-level proof"),
            ("cr-one",),
        ),
        (
            "a plan-level proof entry beside an id on one line is still dropped",
            ("1: plan-level proof, cr-one",),
            ("cr-one",),
        ),
        (
            "an empty name between separators is not a carrier",
            ("1: cr-one, , cr-two",),
            ("cr-one", "cr-two"),
        ),
    ],
)
def test_the_carrier_lines_of_the_block_are_read_as_written(
    label: str, carrier_lines: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert (
        last_carrier_map_carriers(comments=[_event(carrier_lines=carrier_lines)]) == expected
    ), label


def test_the_block_ends_at_the_first_line_that_is_not_a_list_line() -> None:
    """Prose appended after the block is not read as a carrier.

    The clause renders the block LAST, but a comment is prose and a maintainer
    may add a closing line. The block is therefore read positionally and ends
    where its list ends — which is also what keeps a trailing signature from
    becoming a work-item id the plan then waits on.
    """
    text = _BODY + "- 1: cr-one\n\nrecorded under ruling R540."

    assert last_carrier_map_carriers(comments=[{"text": text}]) == ("cr-one",)
