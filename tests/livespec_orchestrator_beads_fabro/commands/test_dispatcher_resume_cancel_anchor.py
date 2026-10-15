"""Whether a stall-cancelled dispatch's own journal row can anchor a resume.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" admits a SECOND anchor beside the proof record: "When no proof
record on the pull request carries the identifier of the item's latest journaled
dispatch, and that dispatch's journal carries a `watchdog-stall-cancel` record
... naming a published head, that cancel record anchors the resume instead." The
same clause bounds it in three ways, and `scenarios.md` Scenario 172 exercises
each: a proof record carrying the dispatch's identifier always wins, the cancel
record anchors only from `proof_capture`, and a record naming no head anchors
nothing.

WHY EACH BOUND IS ASSERTED SEPARATELY RATHER THAN THROUGH ONE HAPPY PATH. All
three produce the SAME observable — no anchor — so a single negative case passes
just as well for a reader that happens to refuse everything. Each case therefore
starts from the anchoring row and breaks exactly one condition, which is what
makes the positive case load-bearing: it is the control that proves the reader
could have returned a hit.

WHY A REWORK-STAGE CANCEL MUST NOT ANCHOR. The clause states the reason outright:
"A cancel in any other stage, including a later `janitor`, `fix` or
`publish_draft` of a rework loop, does not anchor, because its head would not
carry the rework." Anchoring there would resume `proof_capture` on a tree whose
rework is missing, and the record it published would then be proof of a head
nobody built.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_cancel_anchor"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_resume_cancel_anchor.py"
)

_ITEM_ID = "bd-ib-3snvbf"
_OTHER_ITEM_ID = "bd-ib-z6fmp"
_RUN_ID = "01M4Q4XBZ5398FJAWQ131QER60"
_OLDER_RUN_ID = "01M4Q4XBZ5398FJAWQ131QER59"
_HEAD = "c" * 40
_OLDER_HEAD = "d" * 40


def _loaded() -> Any:
    """The module under test, imported inside the body so Red fails on an assertion."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _cancel_row(
    *,
    work_item_id: str = _ITEM_ID,
    run_id: str | None = _RUN_ID,
    executing_stage: str | None = "proof_capture",
    published_head: str | None = _HEAD,
) -> dict[str, object]:
    """One `watchdog-stall-cancel` row, shaped exactly as the cancel site writes it."""
    return {
        "stage": "watchdog-stall-cancel",
        "work_item_id": work_item_id,
        "run_id": run_id,
        "factory": "hp",
        "executing_stage": executing_stage,
        "pull_request": 2639,
        "published_head": published_head,
        "published_head_unreadable": None,
    }


def test_a_cancel_between_publication_and_capture_anchors_the_recorded_head() -> None:
    """The control: the reader CAN return a hit, and it names the run and the head."""
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(_cancel_row(),), work_item_id=_ITEM_ID, proof_run_ids=frozenset()
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID
    assert anchor.head == _HEAD
    assert module.CANCEL_ANCHOR_RESUMED_AT == "proof_capture"


def test_a_journal_holding_no_cancel_row_anchors_nothing() -> None:
    """An item that was never cancelled has no cancel record to anchor from."""
    module = _loaded()
    other: dict[str, object] = {"stage": "dispatch-id", "work_item_id": _ITEM_ID}
    assert (
        module.cancel_anchor(records=(other,), work_item_id=_ITEM_ID, proof_run_ids=frozenset())
        is None
    )


def test_another_items_cancel_row_anchors_nothing_for_this_item() -> None:
    """The journal spans every item, so the row has to be attributed before it is read."""
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(_cancel_row(work_item_id=_OTHER_ITEM_ID),),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )


def test_the_latest_cancel_row_is_the_one_that_anchors() -> None:
    """Journal order is cancellation order, so the newest row is this dispatch's own.

    An earlier cancellation's head belongs to a dispatch the item has since moved
    past; resuming onto it would enter `proof_capture` on a tree two dispatches
    old while the pull request carries the newest one.
    """
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(
            _cancel_row(run_id=_OLDER_RUN_ID, published_head=_OLDER_HEAD),
            _cancel_row(),
        ),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID
    assert anchor.head == _HEAD


def test_a_proof_record_carrying_the_cancelled_runs_identifier_takes_precedence() -> None:
    """ "A proof record that carries the dispatch's identifier always takes precedence."."""
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(_cancel_row(),),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset({_RUN_ID}),
        )
        is None
    )


def test_a_cancel_during_rework_anchors_nothing() -> None:
    """A `janitor`, `fix` or `publish_draft` cancel's head would not carry the rework."""
    module = _loaded()
    for stage in ("janitor", "fix", "publish_draft", None):
        assert (
            module.cancel_anchor(
                records=(_cancel_row(executing_stage=stage),),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )


def test_a_cancel_record_naming_no_head_anchors_nothing() -> None:
    """An unreadable published head is the one case the record states in words.

    Its remedy is NOT a resume: with no head there is nothing to check out and
    nothing to compare the pull request's current head against.
    """
    module = _loaded()
    for head in (None, ""):
        assert (
            module.cancel_anchor(
                records=(_cancel_row(published_head=head),),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )


def test_a_cancel_record_naming_no_run_anchors_nothing() -> None:
    """Without the run id there is no earlier run for the resume record to link."""
    module = _loaded()
    for run_id in (None, ""):
        assert (
            module.cancel_anchor(
                records=(_cancel_row(run_id=run_id),),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )
