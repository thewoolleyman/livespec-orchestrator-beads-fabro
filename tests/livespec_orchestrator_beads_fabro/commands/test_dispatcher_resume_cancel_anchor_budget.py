"""Whether a BUDGET-cancelled dispatch's own journal row can anchor a resume.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" admits the cancel anchor for two stages, not one: "that
dispatch's journal carries a `watchdog-stall-cancel` record **or a
`run-wall-budget-exceeded` record** ... naming a published head, that cancel
record anchors the resume instead". The whole-run wall budget paragraph says the
same thing from its own side — the `run-wall-budget-exceeded` record "anchors
resume ... exactly as a `watchdog-stall-cancel` record does" — and both
sentences arrived in the SAME v133 revision, so neither is a later widening of
the other.

WHY THIS IS ITS OWN MODULE RATHER THAN MORE CASES BESIDE THE STALL ONES. The
stall module's cases are what establish that the reader's bounds hold; these
establish that they hold for the OTHER admitted stage, which is a different
claim and fails for a different reason. Keeping them apart is also what lets
each module's docstring quote the clause for the stage it is about.

WHY THE POSITIVE CASE IS THE LOAD-BEARING ONE. Every negative case here produces
the same observable the pre-repair build produced for EVERY budget row — no
anchor — so a reader that still recognised only the stall stage passes all of
them. Only the control discriminates, and the cost it stands for is measured:
with no anchor the resume refuses for a headless pull request, the re-dispatch
takes the publish-branch reclaim, and the run spends another whole budget
rebuilding implement, janitor and publish_draft — the exact waste the budget
exists to stop.

WHY THE SOURCE IS ASSERTED AND NOT JUST THE ANCHOR. The resume record names the
party that decided the stage, and each source value names the journal STAGE an
operator can grep for. A budget-anchored resume reporting
`watchdog-stall-cancel-record` sends that operator after a row the run's journal
does not carry — an instrument aimed at the wrong population, which answers
cleanly and wrongly rather than failing.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_cancel_anchor"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_resume_cancel_anchor.py"
)

_ITEM_ID = "bd-ib-sdxfsn"
_OTHER_ITEM_ID = "bd-ib-hqt3s5"
_RUN_ID = "01M59EZA51PE9K3R2ZSW0ET7B9"
_STALL_RUN_ID = "01M4Q4XBZ5398FJAWQ131QER60"
_HEAD = "b" * 40
_STALL_HEAD = "e" * 40
_DISPATCH_ID = "be09d09660154fd5ae7a1172a976bcbd"
_LATER_DISPATCH_ID = "1f2e3d4c5b6a79880099aabbccddeeff"

# Spelled as LITERALS and bound to the exported names by one assertion below,
# for the reason this directory's peers record: this module's Red predates the
# constant it binds, and a Red's test bytes are fixed across its Red-to-Green
# pair, so an import of a name that does not exist yet would make the Red a
# collection error rather than a failing assertion.
_BUDGET_SOURCE = "run-wall-budget-exceeded-record"
_STALL_SOURCE = "watchdog-stall-cancel-record"


def _loaded() -> Any:
    """The module under test, imported inside the body so Red fails on an assertion."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _budget_row(
    *,
    work_item_id: str = _ITEM_ID,
    run_id: str | None = _RUN_ID,
    executing_stage: str | None = "proof_capture",
    published_head: str | None = _HEAD,
    dispatch_id: str | None = _DISPATCH_ID,
) -> dict[str, object]:
    """One `run-wall-budget-exceeded` row, shaped as the budget cancel site writes it.

    The stage is the PRODUCTION constant rather than a literal, because the whole
    repair is that this reader and that producer name one stage: a respelling on
    either side would otherwise leave both modules self-consistent while no
    budget row anchored anything.

    The four budget figures ride it because the real row carries them and a
    reader that keyed on their absence would pass here and fail on a live
    journal.
    """
    return {
        "stage": RUN_WALL_BUDGET_EXCEEDED_STAGE,
        "work_item_id": work_item_id,
        "dispatch_id": dispatch_id,
        "run_id": run_id,
        "factory": "hp",
        "executing_stage": executing_stage,
        "pull_request": 2680,
        "published_head": published_head,
        "published_head_unreadable": None,
        "elapsed_seconds": 21_601.0,
        "budget_seconds": 21_600.0,
        "budget_layer": "default",
        "budget_start_source": "run-record",
        "preserved_pointer": "https://github.test/c/9",
    }


def _stall_row(
    *, executing_stage: str | None = "proof_capture", dispatch_id: str | None = _DISPATCH_ID
) -> dict[str, object]:
    """One `watchdog-stall-cancel` row, for the cases that need both stages at once."""
    return {
        "stage": STALL_CANCEL_STAGE,
        "work_item_id": _ITEM_ID,
        "dispatch_id": dispatch_id,
        "run_id": _STALL_RUN_ID,
        "factory": "hp",
        "executing_stage": executing_stage,
        "pull_request": 2680,
        "published_head": _STALL_HEAD,
        "published_head_unreadable": None,
    }


def _dispatch_row(
    *, work_item_id: str = _ITEM_ID, dispatch_id: str | None = _DISPATCH_ID
) -> dict[str, object]:
    """One `dispatch-id` row, which is how the journal records that a dispatch began."""
    return {"stage": "dispatch-id", "work_item_id": work_item_id, "dispatch_id": dispatch_id}


def test_a_budget_cancel_between_publication_and_capture_anchors_the_recorded_head() -> None:
    """The control: the reader CAN return a hit for a budget row, with its own source.

    This is the case the pre-repair build failed, and it failed silently — the
    row was perfectly well-formed, the reader returned `None`, and the resume
    reported a headless pull request as though no run had ever published.
    """
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(_dispatch_row(), _budget_row()),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID
    assert anchor.head == _HEAD
    assert anchor.source == _BUDGET_SOURCE
    assert module.CANCEL_ANCHOR_RESUMED_AT == "proof_capture"


def test_each_cancel_stage_names_the_journal_stage_an_operator_can_grep() -> None:
    """The two sources are DISTINCT and each is its own stage plus `-record`.

    Distinctness is the whole point: one shared value would make the resume
    record unable to say which cancel class decided its stage, and the two have
    different dispositions and different journal rows to look up.
    """
    module = _loaded()
    assert module.SOURCE_CANCEL_RECORD == _STALL_SOURCE
    assert getattr(module, "SOURCE_BUDGET_CANCEL_RECORD") == _BUDGET_SOURCE  # noqa: B009 — bound by name because this module's Red predates the constant.
    assert module.SOURCE_CANCEL_RECORD != module.SOURCE_BUDGET_CANCEL_RECORD
    assert module.SOURCE_CANCEL_RECORD.startswith(STALL_CANCEL_STAGE)
    assert module.SOURCE_BUDGET_CANCEL_RECORD.startswith(RUN_WALL_BUDGET_EXCEEDED_STAGE)


def test_a_stall_row_still_carries_the_stall_source() -> None:
    """The control for the case above: widening the stages did not retire the first.

    Without it, a build that reported the BUDGET source for every cancel row
    would satisfy every budget case in this module while mislabelling every
    stall-anchored resume in the repository.
    """
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(_dispatch_row(), _stall_row()),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert anchor is not None
    assert anchor.run_id == _STALL_RUN_ID
    assert anchor.head == _STALL_HEAD
    assert anchor.source == _STALL_SOURCE


def test_the_latest_cancel_row_answers_across_both_stages() -> None:
    """Journal order is cancellation order, and the order is kept ACROSS the stages.

    A reader that tracked one newest row PER STAGE would answer the stall row
    here, whose head belongs to a cancellation the item has since moved past —
    which is the same wrong tree the single-stage reader reached by a different
    route.
    """
    module = _loaded()
    anchor = module.cancel_anchor(
        records=(_dispatch_row(), _stall_row(), _budget_row()),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert anchor is not None
    assert anchor.run_id == _RUN_ID
    assert anchor.head == _HEAD
    assert anchor.source == _BUDGET_SOURCE
    later = module.cancel_anchor(
        records=(_dispatch_row(), _budget_row(), _stall_row()),
        work_item_id=_ITEM_ID,
        proof_run_ids=frozenset(),
    )
    assert later is not None
    assert later.run_id == _STALL_RUN_ID
    assert later.source == _STALL_SOURCE


def test_a_budget_cancel_during_rework_anchors_nothing() -> None:
    """The stage bound binds the budget row exactly as it binds the stall row.

    "A cancel in any other stage, including a later `janitor`, `fix` or
    `publish_draft` of a rework loop, does not anchor, because its head would not
    carry the rework." The budget cancels a run that is still making progress, so
    a mid-rework budget cancel is the ORDINARY shape here rather than an edge —
    which is what makes the bound worth asserting for this stage.
    """
    module = _loaded()
    for stage in ("janitor", "fix", "publish_draft", "implement", None, ""):
        assert (
            module.cancel_anchor(
                records=(_dispatch_row(), _budget_row(executing_stage=stage)),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )


def test_a_budget_row_naming_no_head_anchors_nothing() -> None:
    """A budget cancel before any `publish_draft` completed has no tree to resume.

    The budget record states that condition in words — it carries the same
    published-head rules as the stall record, "including stating that the head
    could not be read when it cannot" — and this is the reader computing the same
    conclusion from the absent value.
    """
    module = _loaded()
    for head in (None, ""):
        assert (
            module.cancel_anchor(
                records=(_dispatch_row(), _budget_row(published_head=head)),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )


def test_a_budget_row_naming_no_run_anchors_nothing() -> None:
    """Without the run id there is no earlier run for the resume record to link."""
    module = _loaded()
    for run_id in (None, ""):
        assert (
            module.cancel_anchor(
                records=(_dispatch_row(), _budget_row(run_id=run_id)),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset(),
            )
            is None
        )


def test_another_items_budget_row_anchors_nothing_for_this_item() -> None:
    """The journal spans every item, so the row has to be attributed before it is read."""
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(_budget_row(work_item_id=_OTHER_ITEM_ID),),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )


def test_a_proof_record_carrying_the_budget_cancelled_dispatch_takes_precedence() -> None:
    """ "A proof record that carries the dispatch's identifier always takes precedence."

    Asserted for BOTH identifiers one dispatch is attributed by, because the
    budget row carries both and a rule comparing only the run id would anchor
    here — re-entering `proof_capture` for a dispatch whose capture had already
    completed and been reviewed.
    """
    module = _loaded()
    for identifier in (_RUN_ID, _DISPATCH_ID):
        assert (
            module.cancel_anchor(
                records=(_dispatch_row(), _budget_row()),
                work_item_id=_ITEM_ID,
                proof_run_ids=frozenset({identifier}),
            )
            is None
        )


def test_a_budget_row_the_item_has_since_dispatched_past_anchors_nothing() -> None:
    """The anchor is scoped to the item's LATEST journaled dispatch, either stage.

    Both halves of the supersession reading are asserted: a `dispatch-id` row
    AFTER the budget row (position), and a budget row naming a dispatch other
    than the latest (identity). Anchoring on a superseded budget row is wrong in
    both directions at once — it either fires the moved-head refusal on a
    two-dispatches-old sha and names a plain dispatch as the remedy, reclaiming
    the publish branch, or re-captures a tree already proved.
    """
    module = _loaded()
    assert (
        module.cancel_anchor(
            records=(
                _dispatch_row(),
                _budget_row(),
                _dispatch_row(dispatch_id=_LATER_DISPATCH_ID),
            ),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )
    assert (
        module.cancel_anchor(
            records=(_dispatch_row(dispatch_id=_LATER_DISPATCH_ID), _budget_row()),
            work_item_id=_ITEM_ID,
            proof_run_ids=frozenset(),
        )
        is None
    )


def test_a_rework_stage_budget_cancel_reports_its_unanchoring_stage() -> None:
    """The refusal explains a head-naming budget row it refused, and nothing else.

    `unanchoring_cancel_stage` answers the same question about the same row the
    decision read, so widening the decision's stages without widening this one
    would leave a budget-refused resume unable to state the whole of its
    condition. The no-head case is the sharp one: a `janitor` budget cancel whose
    head was unreadable is the NO-HEAD case, so reporting its stage would offer
    the rework rule as the reason when the real reason is that nothing was
    measured.
    """
    module = _loaded()
    assert (
        module.unanchoring_cancel_stage(
            records=(_dispatch_row(), _budget_row(executing_stage="janitor")),
            work_item_id=_ITEM_ID,
        )
        == "janitor"
    )
    for row in (
        _budget_row(executing_stage="janitor", published_head=None),
        _budget_row(executing_stage="janitor", published_head=""),
        _budget_row(executing_stage=None),
        _budget_row(executing_stage=""),
        _budget_row(),
        _budget_row(work_item_id=_OTHER_ITEM_ID, executing_stage="janitor"),
    ):
        assert (
            module.unanchoring_cancel_stage(records=(_dispatch_row(), row), work_item_id=_ITEM_ID)
            is None
        )
