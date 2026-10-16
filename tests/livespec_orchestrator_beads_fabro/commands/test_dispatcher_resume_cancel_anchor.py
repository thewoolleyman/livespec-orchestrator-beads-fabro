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


_DISPATCH_ID = "7a636b5e7d60425c942ebdaf10fe7e53"


def test_a_proof_record_carrying_the_cancelled_dispatch_id_also_takes_precedence() -> None:
    """The second of the two identifiers one dispatch is attributed by.

    `_dispatcher_proof_attribution` accepts a record naming a dispatch by either
    its run id or its dispatch id, and the cancel row names both, so the
    precedence test has to ask about both. A rule comparing only the run id
    passes the run-id case above and silently anchors on the cancel row here —
    re-entering `proof_capture` for a dispatch whose capture had completed.
    """
    module = _loaded()
    row = _cancel_row()
    row["dispatch_id"] = _DISPATCH_ID
    assert (
        module.cancel_anchor(
            records=(row,),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset({_DISPATCH_ID}),
        )
        is None
    )


def test_a_row_naming_no_dispatch_id_still_anchors_on_its_run_id_alone() -> None:
    """An older row predating the dispatch-id field is still a good anchor.

    The only thing an absent dispatch id costs is the second precedence
    comparison, so the arm degrades to the run id rather than refusing — a row
    that cannot be cross-checked both ways is not a row that anchors nothing.
    """
    module = _loaded()
    row = _cancel_row()
    row["dispatch_id"] = None
    anchor = module.cancel_anchor(
        records=(row,), work_item_id=_ITEM_ID, proof_run_ids=frozenset({_DISPATCH_ID})
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID


def test_only_a_rework_stage_cancel_naming_a_head_reports_an_unanchoring_stage() -> None:
    """The refusal explains a head-naming row it refused, and nothing else.

    Each case below is a row that cannot anchor, and only the first leaves an
    operator with a head-naming record to wonder about. The no-head cases are the
    sharp ones: a `janitor` cancel whose head was unreadable is the NO-HEAD case,
    so reporting its stage would offer the rework rule as the reason a resume
    cannot proceed when the real reason is that nothing was measured.
    """
    module = _loaded()
    assert (
        module.unanchoring_cancel_stage(
            records=(_cancel_row(executing_stage="janitor"),), work_item_id=_ITEM_ID
        )
        == "janitor"
    )
    for row in (
        _cancel_row(executing_stage="janitor", published_head=None),
        _cancel_row(executing_stage="janitor", published_head=""),
        _cancel_row(executing_stage=None),
        _cancel_row(executing_stage=""),
        _cancel_row(),
        _cancel_row(work_item_id=_OTHER_ITEM_ID, executing_stage="janitor"),
    ):
        assert module.unanchoring_cancel_stage(records=(row,), work_item_id=_ITEM_ID) is None


_LATER_DISPATCH_ID = "a7395318d0c945589105940e7936139f"


def _dispatch_row(
    *, work_item_id: str = _ITEM_ID, dispatch_id: str | None = _DISPATCH_ID
) -> dict[str, object]:
    """One `dispatch-id` row, which is how the journal records that a dispatch began."""
    return {"stage": "dispatch-id", "work_item_id": work_item_id, "dispatch_id": dispatch_id}


def _cancelled_dispatch(*, dispatch_id: str | None = _DISPATCH_ID) -> dict[str, object]:
    """One anchoring cancel row that names the dispatch it belongs to."""
    row = _cancel_row()
    row["dispatch_id"] = dispatch_id
    return row


def test_a_cancel_row_the_item_has_since_dispatched_past_anchors_nothing() -> None:
    """The clause scopes this anchor to the item's LATEST journaled dispatch.

    "When no proof record on the pull request carries the identifier of the
    item's latest journaled dispatch, and THAT dispatch's journal carries a
    `watchdog-stall-cancel` record" — so a cancel row belonging to a dispatch a
    later plain dispatch has superseded is not this anchor, however recent it is
    among the cancel rows. The journal is append-only and a `dispatch-id` row is
    written at launch, so a `dispatch-id` row for the item AFTER the cancel row
    is a dispatch that began later and was never cancelled.

    Anchoring there is wrong in both directions at once, and both are expensive.
    When the pull request carries the later dispatch's head, the moved-head
    refusal fires on a two-dispatches-old sha and names a plain dispatch as the
    remedy — which reclaims the publish branch this whole item exists to
    preserve. When the two heads coincide, the resume re-enters `proof_capture`
    on a tree the later dispatch had already captured and had reviewed.
    """
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(
                _dispatch_row(),
                _cancelled_dispatch(),
                _dispatch_row(dispatch_id=_LATER_DISPATCH_ID),
            ),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )


def test_the_latest_dispatchs_own_cancel_row_still_anchors() -> None:
    """The control for the gate above: a row of the latest dispatch is admitted.

    Without it, a gate that refused every journal carrying a `dispatch-id` row
    at all would satisfy the supersession case while retiring the anchor
    entirely — and every journal of a real dispatch carries one. The unrelated
    row is here for the same reason: the gate reads the item's DISPATCH rows,
    not every row the item has.
    """
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(
            _dispatch_row(work_item_id=_OTHER_ITEM_ID, dispatch_id=_LATER_DISPATCH_ID),
            _dispatch_row(),
            {"stage": "ledger-admit", "work_item_id": _ITEM_ID},
            _cancelled_dispatch(),
        ),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID
    assert anchor.head == _HEAD


def test_a_cancel_row_naming_a_dispatch_other_than_the_latest_anchors_nothing() -> None:
    """Position is not the whole of attribution, so the named ids are compared too.

    A cancel row can be journaled AFTER the dispatch it belongs to has been
    superseded — a reconciliation of a stranded run writes one — and such a row
    sits last in the journal while naming a dispatch the item has moved past.
    Journal position cannot tell that row from the latest dispatch's own; the
    two dispatch ids can, and they are both already on the records.
    """
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(_dispatch_row(dispatch_id=_LATER_DISPATCH_ID), _cancelled_dispatch()),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )


def test_a_proof_record_naming_the_latest_journaled_dispatch_takes_precedence() -> None:
    """The precedence comparison takes the LATEST DISPATCH's identifiers, not the row's.

    The two are the same set whenever the cancel row names its dispatch, which is
    why this case names none: a row written before the cancel site recorded the
    dispatch id still belongs to the dispatch the `dispatch-id` row identifies,
    so a proof record carrying THAT id is evidence this dispatch's capture
    completed and outranks the row exactly as a run-id-bearing record does.
    """
    module = _loaded()
    records = (_dispatch_row(), _cancelled_dispatch(dispatch_id=None))
    assert (
        module.cancel_anchor(
            records=records, work_item_id=_ITEM_ID, proof_run_ids=frozenset({_DISPATCH_ID})
        )
        is None
    )
    anchor = module.cancel_anchor(records=records, work_item_id=_ITEM_ID, proof_run_ids=frozenset())
    assert anchor is not None
    assert anchor.run_id == _RUN_ID


def test_a_superseded_rework_stage_cancel_reports_no_unanchoring_stage() -> None:
    """The refusal's explanation is scoped to the same dispatch its decision is.

    Both readings resolve the row through one gate, so the refusal cannot offer
    the rework rule as its reason while naming a cancel from a dispatch the item
    has already dispatched past — an explanation that would send an operator
    hunting a rework loop that is not what refused them.
    """
    module = _loaded()
    rework = _cancel_row(executing_stage="janitor")
    rework["dispatch_id"] = _DISPATCH_ID
    assert (
        module.unanchoring_cancel_stage(
            records=(_dispatch_row(), rework, _dispatch_row(dispatch_id=_LATER_DISPATCH_ID)),
            work_item_id=_ITEM_ID,
        )
        is None
    )
    assert (
        module.unanchoring_cancel_stage(records=(_dispatch_row(), rework), work_item_id=_ITEM_ID)
        == "janitor"
    )
