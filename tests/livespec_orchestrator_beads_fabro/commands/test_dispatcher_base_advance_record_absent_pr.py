"""The overtaken-arming record's pull-request FIGURE when the ending named none.

The sibling module `test_dispatcher_base_advance_record` grades the three ways
a NAME can reach the body — passable, unpassable, unreported. This is the
fourth reading and it is not a name: `DispatchOutcome.pr_number` is typed
`int | None`, so the public renderer's `pr_number` parameter is too, and the
v145 "Armed pull request overtaken by the default branch" clause requires the
comment to carry "the pull request number" among its figures.

WHY IT IS ITS OWN CASE RATHER THAN A FIFTH READING IN THE SIBLING'S UNREPORTED
CASE. The clause's left-out COUNT is about names, and the count exists so an
operator can tell how much of the record is missing. A figure the ending never
recorded must therefore be stated WITHOUT touching that count: a renderer that
folded it in would report `1 names were left out` for a record whose every
name is present and correct, which is a false statement about the one field a
triaging operator reads to decide whether the record is trustworthy. Asserting
the count stays at zero is what separates the two, and no case that supplies a
pull-request number can take it.

The module is imported inside the test body for the same reason the sibling
gives: a top-level import of a module under construction makes a Red a
collection error rather than a genuine assertion failure.
"""

from __future__ import annotations

import importlib

_RECORD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record"

_ITEM_ID = "bd-ib-overtaken"
_RUN_ID = "01M509QRWWNKK6H8VK865JGFC9"
_FACTORY = "hp"
_PR_HEAD = "f4e0538675a6a27767a0fe92c3f992239c388da5"
_BASE_TIP = "95c10648d28cdb42ebfed84887bf7bdd421b0955"


def test_an_unrecorded_pull_request_number_is_stated_and_not_counted_as_a_name() -> None:
    module = importlib.import_module(_RECORD_MODULE)

    body = module.base_advanced_comment_body(  # type: ignore[attr-defined]
        work_item_id=_ITEM_ID,
        run_id=_RUN_ID,
        factory=_FACTORY,
        pr_number=None,
        pr_head=_PR_HEAD,
        default_branch_tip=_BASE_TIP,
    )

    # The line is RENDERED rather than omitted: an absent `pull request:` line
    # is what a record from a build predating the field looks like, so a reader
    # could not tell "none was named" from "this record never carried the key".
    pull_request_lines = [line for line in body.splitlines() if line.startswith("pull request: ")]
    assert len(pull_request_lines) == 1
    assert "not reported" in pull_request_lines[0]

    # A figure is not a name, so the clause's left-out count is untouched, and
    # every name this record did carry is still in it.
    assert "0 names were left out" in body
    assert _PR_HEAD in body
    assert _BASE_TIP in body
