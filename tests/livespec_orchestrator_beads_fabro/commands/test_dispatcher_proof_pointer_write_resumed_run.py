"""Which dispatch the pointer of a resumed item credits, and when it credits none.

The resume clause of `SPECIFICATION/contracts.md` says "The Proof of Done pointer
written for a resumed item MUST name the resumed run's identifier beside the
record's own run id". Those two differ exactly because the record was published by
the EARLIER run — which is the whole point of a resume — so the value the pointer
needs is the MERGING dispatch's identifier, and the journal is consulted only to
answer whether this merge was reached through a resume at all.

THREE NEGATIVE CASES ARE ASSERTED, and each is a different way the bullet could be
written dishonestly:

- an item with no resume record is an ordinary dispatch, whose pointer must render
  byte-for-byte as it did before this field existed;
- an item whose EARLIER pull request was resumed and whose current one was
  dispatched plainly was not resumed into this merge, so naming a resumed run
  would credit a dispatch that had nothing to do with the record being cited;
- a merge whose outcome carries no run id — which is every `reconcile-merged`
  outcome, built from a resolved merged pull request — has no identifier to name,
  and a blank bullet reads as an identifier that was recorded and lost.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    resumed_run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-fngpwg"
_MERGING_RUN = "01M4RESUMEDRUN"
_PULL_REQUEST = 2639
_HEAD = "a" * 40


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="acceptance",
        title="A terminated run is resumed from its pull request",
        description="## Definition of Done\n\n- The resume enters at the unfinished stage.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, fabro_run_id: str | None = _MERGING_RUN) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=_PULL_REQUEST,
        merge_sha="b" * 40,
        detail="merged",
        fabro_run_id=fabro_run_id,
    )


def _journal(*, tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "dispatch-journal.jsonl"
    _ = path.write_text(
        "".join(f"{json.dumps(row)}\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _resume_row(*, pull_request: int) -> dict[str, object]:
    return resume_journal_record(
        work_item_id=_ITEM_ID,
        earlier_run_ids=("01M4EARLIER",),
        pull_request=pull_request,
        head=_HEAD,
        resumed_at="pr",
        source="pull-request-latest-record",
    )


def test_a_resumed_merge_credits_the_merging_dispatch(tmp_path: Path) -> None:
    """The identifier named is the dispatch that merged, not the one that proved."""
    journal_path = _journal(tmp_path=tmp_path, rows=[_resume_row(pull_request=_PULL_REQUEST)])
    assert (
        resumed_run_id(
            journal_path=journal_path,
            item=_item(),
            outcome=_outcome(),
            pull_request=_PULL_REQUEST,
        )
        == _MERGING_RUN
    )


def test_an_ordinary_dispatch_credits_nobody(tmp_path: Path) -> None:
    """Without a resume record the pointer renders as it always did."""
    journal_path = _journal(tmp_path=tmp_path, rows=[])
    assert (
        resumed_run_id(
            journal_path=journal_path,
            item=_item(),
            outcome=_outcome(),
            pull_request=_PULL_REQUEST,
        )
        is None
    )


def test_a_resume_of_an_earlier_pull_request_credits_nobody_here(tmp_path: Path) -> None:
    """A once-resumed item's plainly-dispatched pull request was not resumed."""
    journal_path = _journal(tmp_path=tmp_path, rows=[_resume_row(pull_request=2581)])
    assert (
        resumed_run_id(
            journal_path=journal_path,
            item=_item(),
            outcome=_outcome(),
            pull_request=_PULL_REQUEST,
        )
        is None
    )


def test_an_outcome_with_no_run_id_credits_nobody(tmp_path: Path) -> None:
    """A blank bullet would read as an identifier recorded and lost."""
    journal_path = _journal(tmp_path=tmp_path, rows=[_resume_row(pull_request=_PULL_REQUEST)])
    assert (
        resumed_run_id(
            journal_path=journal_path,
            item=_item(),
            outcome=_outcome(fabro_run_id=None),
            pull_request=_PULL_REQUEST,
        )
        is None
    )
