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
    """A fresh pull request starts the bound over; the previous one's are not its."""
    module = _journal_module()
    records = [
        _resume_row(pull_request=2581, earlier_run_ids=("01M4ONE",)),
        _resume_row(pull_request=2581, earlier_run_ids=("01M4TWO",)),
        _resume_row(pull_request=2639, earlier_run_ids=("01M4THREE",)),
    ]
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2581) == (
        "01M4ONE",
        "01M4TWO",
    )
    assert module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639) == (
        "01M4THREE",
    )


def test_a_resume_naming_no_identifier_still_counts_toward_the_bound() -> None:
    """A malformed row must not silently raise the cap by one."""
    module = _journal_module()
    records = [{"stage": module.RESUME_STAGE, "work_item_id": _ITEM, "pull_request": 2639}]
    anchored = module.resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=2639)
    assert len(anchored) == 1


def test_was_resumed_is_keyed_on_the_pull_request() -> None:
    """A plainly-dispatched pull request of a once-resumed item was not resumed."""
    module = _journal_module()
    records = [_resume_row(pull_request=2581)]
    assert module.was_resumed(records=records, work_item_id=_ITEM, pull_request=2581) is True
    assert module.was_resumed(records=records, work_item_id=_ITEM, pull_request=2639) is False
