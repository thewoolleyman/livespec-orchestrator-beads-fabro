"""The `resume` journal record, and the attribution chain it carries.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" requires one `resume` record journaled BEFORE the run exists,
naming the earlier run's identifiers, the pull request number, the published head,
the resumed-at stage and the source that decided it. Its attribution paragraph
then makes that record load-bearing: the acceptance pass MUST attribute a record
carrying any identifier the chain links to the resumed dispatch, "so a `verified`
record the earlier run published grades the resumed run's merge".

WHY THE TRANSITIVE CASE IS ASSERTED. The clause admits a SECOND resume, and
Scenario 142 says attribution then follows "through the two resume records". A
reader that returned only the newest resume's identifiers would attribute the
SECOND run's records and drop the first run's — which is the run that captured
and verified, so every factory-captured assertion would come back unevidenced and
the item would park on NEEDS_ATTENTION with its proof sitting on the pull request.

WHY THE PULL-REQUEST KEY IS ASSERTED SEPARATELY FROM THE ITEM KEY. An item can
legitimately have more than one pull request over its life: a plain re-dispatch
after a reclaim opens a new one. The third-resume bound counts resumes anchored
on ONE pull request, so a per-item count would refuse a first resume of a freshly
published pull request because two resumes of a previous one had been spent.

WHY A MALFORMED ROW IS ASSERTED TOO. A journal row is JSON an earlier build
wrote, so a field may be absent or carry the wrong type. Each such reading must
yield NO identifier rather than a coerced one: a `str()`-ed non-string looks like
an id and matches nothing, which reads as a record belonging to another item
rather than as a malformed row. And such a row must still COUNT toward the resume
bound, or a malformed record would silently raise the cap by one.

WHY THE BOUND IS ASSERTED AGAINST RESUMES THAT CREATED A RUN, NOT AGAINST
ATTEMPTS. The record is journaled BEFORE the run exists, so a `resume` row is
evidence of an attempt. The bound exists because "the proof-loop caps are per
run", so an attempt refused before any run was created spent none of them and
anchored nothing. Measured 2026-10-18 on `bd-ib-nsrgxl`: two resume attempts of
pull request 3209 were each refused by the ACP preflight's session-headroom
filter with no Fabro run, and the third was refused for having "already anchored
2 resumes" — so a transient provider-headroom refusal had permanently cost the
item its resume route, leaving only a plain dispatch, which reclaims the publish
branch and discards the pull request's approved work.

Each case here therefore says which rows name a run. The negative cases are the
load-bearing ones and they come in two shapes, because a reader keyed on "has
this item ever had a run" would satisfy the first and fail the second: an attempt
with NO run-naming row after it, and an attempt whose window is closed by the
item's NEXT attempt before any run appears — one launched resume must not vouch
for the refused attempt that preceded it.

WHY THE POINTER READER IS ASSERTED NOT TO NARROW WITH IT. `was_resumed` answers a
different question — whether the MERGE an item reached was reached through a
resume — and is asked only of an item that merged, whose resumed-run identifier
comes from the merging outcome rather than from the journal. Narrowing it would
make a pointer's provenance depend on a row the merging dispatch does not own, so
the asymmetry is asserted directly rather than left to be rediscovered as a bug.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_journal.py"
)

_ITEM = "bd-ib-fngpwg"
_OTHER_ITEM = "bd-ib-ocjy4t"
_HEAD = "a" * 40


def _journal_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _resume_row(
    *,
    work_item_id: str = _ITEM,
    earlier_run_ids: Any = ("01M4EARLIER",),
    pull_request: int = 2639,
    resumed_at: str = "pr",
) -> dict[str, object]:
    module = _journal_module()
    return module.resume_journal_record(
        work_item_id=work_item_id,
        earlier_run_ids=earlier_run_ids,
        pull_request=pull_request,
        head=_HEAD,
        resumed_at=resumed_at,
        source=module.SOURCE if hasattr(module, "SOURCE") else "pull-request-latest-record",
    )


def _run_row(*, work_item_id: str = _ITEM, run_id: str = "01M4LAUNCHED") -> dict[str, object]:
    """A row naming a factory run for one item, as every launched dispatch writes.

    `dispatch-run-stamp` is the stage a dispatch writes on first sight of its run
    id, but the STAGE is deliberately not what the reader keys on: a record counts
    as naming a run when it carries both a `work_item_id` and a `run_id`, which is
    the reading `_run_attribution` owns and the one a stage added later cannot
    silently fall out of.
    """
    return {"stage": "dispatch-run-stamp", "work_item_id": work_item_id, "run_id": run_id}


def _refused_row(*, work_item_id: str = _ITEM) -> dict[str, object]:
    """The ACP preflight's own refusal row: an attempt that reached no factory.

    It names no run because there is none — which is the whole condition under
    test, and the measured one.
    """
    return {
        "stage": "acp-preflight-refusal",
        "work_item_id": work_item_id,
        "detail": "session-headroom-shortfall",
    }


def test_the_record_names_everything_the_clause_requires() -> None:
    """The earlier run, the pull request, the head, the stage and the source."""
    module = _journal_module()
    record = _resume_row()
    assert record["stage"] == module.RESUME_STAGE
    assert record["work_item_id"] == _ITEM
    assert record["earlier_run_ids"] == ["01M4EARLIER"]
    assert record["pull_request"] == 2639
    assert record["head"] == _HEAD
    assert record["resumed_at"] == "pr"
    assert record["resumed_at_source"] == "pull-request-latest-record"


def test_both_of_the_earlier_runs_identifiers_are_recorded() -> None:
    """The clause accepts either identifier, so linking only one links half the pair."""
    module = _journal_module()
    record = module.resume_journal_record(
        work_item_id=_ITEM,
        earlier_run_ids=("01M4RUN", "dispatch-id-hex"),
        pull_request=2639,
        head=_HEAD,
        resumed_at="review",
        source="factory-run-record",
    )
    assert record["earlier_run_ids"] == ["01M4RUN", "dispatch-id-hex"]


def test_the_chain_unions_every_resume_of_the_item() -> None:
    """A second resume must not drop the run that captured and verified."""
    module = _journal_module()
    records = [
        _resume_row(earlier_run_ids=("01M4FIRST",)),
        _resume_row(earlier_run_ids=("01M4SECOND",)),
    ]
    assert module.resume_linked_run_ids(records=records, work_item_id=_ITEM) == (
        "01M4FIRST",
        "01M4SECOND",
    )


def test_the_chain_ignores_another_items_resumes() -> None:
    """A resume of a different item links nothing here."""
    module = _journal_module()
    records = [_resume_row(work_item_id=_OTHER_ITEM, earlier_run_ids=("01M4THEIRS",))]
    assert module.resume_linked_run_ids(records=records, work_item_id=_ITEM) == ()


def test_the_chain_ignores_rows_of_other_stages() -> None:
    """Only `resume` rows link identifiers; a dispatch row is not one."""
    module = _journal_module()
    records = [{"stage": "dispatch", "work_item_id": _ITEM, "earlier_run_ids": ["01M4NOPE"]}]
    assert module.resume_linked_run_ids(records=records, work_item_id=_ITEM) == ()


def test_duplicate_identifiers_are_dropped() -> None:
    """Two resumes naming one earlier run link it once."""
    module = _journal_module()
    records = [_resume_row(), _resume_row()]
    assert module.resume_linked_run_ids(records=records, work_item_id=_ITEM) == ("01M4EARLIER",)


def test_a_malformed_identifier_field_links_nothing() -> None:
    """A coerced non-string would look like an id and match no record."""
    module = _journal_module()
    for malformed in (None, "01M4SCALAR", 7, [None, 7]):
        records = [{"stage": module.RESUME_STAGE, "work_item_id": _ITEM}]
        records[0]["earlier_run_ids"] = malformed
        assert module.resume_linked_run_ids(records=records, work_item_id=_ITEM) == ()


def test_resumes_are_counted_per_pull_request() -> None:
    """A fresh pull request starts the bound over; the previous one's are not its.

    Every resume here goes on to create a run, which is what makes the three
    counted at all. The LEADING run row is the dispatch that published the pull
    request in the first place: it precedes every attempt, so it also pins that a
    run predating an attempt cannot be read as that attempt's own.
    """
    module = _journal_module()
    records = [
        _run_row(run_id="01M4PUBLISHED"),
        _resume_row(pull_request=2581, earlier_run_ids=("01M4ONE",)),
        _run_row(run_id="01M4FIRSTRESUMED"),
        _resume_row(pull_request=2581, earlier_run_ids=("01M4TWO",)),
        _run_row(run_id="01M4SECONDRESUMED"),
        _resume_row(pull_request=2639, earlier_run_ids=("01M4THREE",)),
        _run_row(run_id="01M4THIRDRESUMED"),
    ]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2581) == (
        "01M4ONE",
        "01M4TWO",
    )
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == (
        "01M4THREE",
    )


def test_a_resume_naming_no_identifier_still_counts_toward_the_bound() -> None:
    """A malformed row that DID create a run must not silently raise the cap by one."""
    module = _journal_module()
    records = [
        {"stage": module.RESUME_STAGE, "work_item_id": _ITEM, "pull_request": 2639},
        _run_row(),
    ]
    anchored = module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639)
    assert len(anchored) == 1


def test_a_resume_refused_before_any_run_anchors_nothing() -> None:
    """The bound replaces caps that are per RUN, so an attempt with none spent none."""
    module = _journal_module()
    records = [_resume_row(earlier_run_ids=("01M4ONE",)), _refused_row()]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == ()


def test_two_resumes_refused_before_any_run_leave_the_bound_unspent() -> None:
    """Scenario 143's third-resume refusal is premised on two ANCHORED resumes.

    This is the measured journal: two attempts, each refused by the session-
    headroom filter with no Fabro run between them, and nothing for the bound to
    have counted.
    """
    module = _journal_module()
    records = [
        _resume_row(earlier_run_ids=("01M4ONE",)),
        _refused_row(),
        _resume_row(earlier_run_ids=("01M4TWO",)),
        _refused_row(),
    ]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == ()


def test_a_launched_resume_does_not_vouch_for_the_attempt_before_it() -> None:
    """The window closes at the item's next attempt, or one run would cover two.

    Without the bound closing there, a reader would answer "has this item ever had
    a run" — which the preceding case cannot distinguish, because it has none at
    all — and both attempts would count off the one run the second created.
    """
    module = _journal_module()
    records = [
        _resume_row(earlier_run_ids=("01M4REFUSED",)),
        _resume_row(earlier_run_ids=("01M4RESUMED",)),
        _run_row(),
    ]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == (
        "01M4RESUMED",
    )


def test_another_items_run_does_not_anchor_this_items_resume() -> None:
    """One journal serves every item, so a concurrent dispatch's run is not ours."""
    module = _journal_module()
    records = [_resume_row(earlier_run_ids=("01M4ONE",)), _run_row(work_item_id=_OTHER_ITEM)]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == ()


def test_the_pointer_reader_does_not_narrow_with_the_bound() -> None:
    """`was_resumed` asks whether a MERGE was reached through a resume, not the cap.

    It is consulted only for an item that merged, and the identifier its pointer
    names comes from the merging outcome rather than from the journal, so an
    attempt that created no run cannot be the dispatch it credits. Narrowing it
    alongside the bound would make a pointer's provenance depend on a row the
    merging dispatch does not own.
    """
    module = _journal_module()
    records = [_resume_row(earlier_run_ids=("01M4ONE",)), _refused_row()]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == ()
    assert module.was_resumed(records=records, work_item_id=_ITEM, pull_request=2639) is True


def test_was_resumed_is_keyed_on_the_pull_request() -> None:
    """A plainly-dispatched pull request of a once-resumed item was not resumed."""
    module = _journal_module()
    records = [_resume_row(pull_request=2581)]
    assert module.was_resumed(records=records, work_item_id=_ITEM, pull_request=2581) is True
    assert module.was_resumed(records=records, work_item_id=_ITEM, pull_request=2639) is False
