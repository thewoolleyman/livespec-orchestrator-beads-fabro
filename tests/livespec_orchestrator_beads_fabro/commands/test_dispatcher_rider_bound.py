"""A rendered goal and the judgement subject carry a bounded rider set (bd-ib-l2poch).

`contracts.md`, in its dispatch-brief lessons injection part, says a goal carries a
bounded rider set: of an item's riders the goal carries those appended after the item's
most recent dispatch claim, plus every `STANDING RIDER:` and every
`FOR <stage>[, <stage>...] ONLY:` rider whatever its age, and states in ONE line how
many riders it left out, the creation time of the newest one and the command that
lists the item's full ledger comments. Measured on bd-ib-uq2ocd: 88 comments,
1,628,501 characters, every host taking ended at the input bound.

EVERY NEGATIVE CLAIM IS PAIRED WITH ITS CONTROL. "The goal leaves a rider out" is
satisfied by a renderer that leaves every rider out, so each case asserts the
omitted rider beside a carried one that differs in exactly one input, and the
"digest did not move" case beside one where a carried rider does move it.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_judgement_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound"
_ITEM_ID = "bd-ib-l2poch"
_CLAIM = "2026-11-10T06:00:00Z"
_BEFORE = "2026-11-09T06:00:00Z"
_AFTER = "2026-11-10T07:00:00Z"
_OLD_RIDER = "OLD-UNSCOPED-RIDER: tighten the first assertion."
_NEW_RIDER = "NEW-UNSCOPED-RIDER: also cover the second assertion."
_STANDING = "STANDING RIDER: never run git push.\nReason: R78."
_SCOPED = "FOR proof_capture, review ONLY: stay read-only."


def _bound() -> object:
    module_path = Path(importlib.import_module("livespec_orchestrator_beads_fabro").__file__ or "")
    expected = module_path.parent / "commands" / "_dispatcher_rider_bound.py"
    assert expected.is_file(), f"{expected} does not exist yet"
    return importlib.import_module(_MODULE)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="Bound the riders",
        description="## Definition of Done\n\n- The goal is bounded.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _comment(text: str, created_at: str | None) -> WorkItemComment:
    return WorkItemComment(text=text, author="Chad", created_at=created_at)


def _goal(*, comments: tuple[WorkItemComment, ...], claim_at: str | None) -> str:
    return render_goal(
        item=_item(), repo=Path("/nonexistent"), branch="b", comments=comments, claim_at=claim_at
    )


def _journal(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True)
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_a_rider_older_than_the_last_claim_is_left_out_and_a_newer_one_is_carried() -> None:
    goal = _goal(
        comments=(_comment(_OLD_RIDER, _BEFORE), _comment(_NEW_RIDER, _AFTER)),
        claim_at=_CLAIM,
    )

    assert _NEW_RIDER in goal
    assert _OLD_RIDER not in goal
    left_out_lines = [line for line in goal.splitlines() if "left out" in line]
    assert len(left_out_lines) == 1
    assert "1 rider" in left_out_lines[0]
    assert _BEFORE in left_out_lines[0]
    assert f"bd comments {_ITEM_ID}" in left_out_lines[0]


def test_the_left_out_line_names_the_newest_left_out_rider_and_pluralizes() -> None:
    goal = _goal(
        comments=(
            _comment("first old", "2026-11-01T00:00:00Z"),
            _comment("second old", "2026-11-08T00:00:00Z"),
            _comment("third old", "2026-11-03T00:00:00Z"),
        ),
        claim_at=_CLAIM,
    )

    line = next(line for line in goal.splitlines() if "left out" in line)
    assert "3 riders" in line
    assert "2026-11-08T00:00:00Z" in line
    assert "2026-11-03T00:00:00Z" not in line


def test_standing_and_stage_scoped_riders_are_carried_whatever_their_age() -> None:
    goal = _goal(
        comments=(
            _comment(_STANDING, _BEFORE),
            _comment(_SCOPED, _BEFORE),
            _comment(_OLD_RIDER, _BEFORE),
        ),
        claim_at=_CLAIM,
    )

    assert "STANDING RIDER: never run git push." in goal
    assert _SCOPED in goal
    assert _OLD_RIDER not in goal
    assert "1 rider" in goal


def test_a_goal_with_nothing_left_out_states_no_left_out_line() -> None:
    goal = _goal(
        comments=(_comment(_NEW_RIDER, _AFTER), _comment(_STANDING, _BEFORE)), claim_at=_CLAIM
    )

    assert _NEW_RIDER in goal
    assert "left out" not in goal


def test_an_item_never_claimed_carries_every_rider_and_states_no_left_out_line() -> None:
    goal = _goal(
        comments=(
            _comment(_OLD_RIDER, _BEFORE),
            _comment("second", "2026-11-02T00:00:00Z"),
            _comment("third", "2026-11-03T00:00:00Z"),
        ),
        claim_at=None,
    )

    assert _OLD_RIDER in goal
    assert "second" in goal
    assert "third" in goal
    assert "left out" not in goal


def test_a_receipt_is_never_counted_as_a_left_out_rider() -> None:
    receipt = f"{JUDGEMENT_COMMENT_MARKER}\nverdict: passed"
    goal = _goal(
        comments=(_comment(receipt, _BEFORE), _comment(_OLD_RIDER, _BEFORE)),
        claim_at=_CLAIM,
    )

    line = next(line for line in goal.splitlines() if "left out" in line)
    assert "1 rider" in line
    assert JUDGEMENT_COMMENT_MARKER not in goal


def test_a_goal_whose_every_rider_is_left_out_still_states_the_line() -> None:
    goal = _goal(comments=(_comment(_OLD_RIDER, _BEFORE),), claim_at=_CLAIM)

    assert _OLD_RIDER not in goal
    assert "1 rider" in goal
    assert f"bd comments {_ITEM_ID}" in goal


def test_a_rider_with_no_readable_creation_time_is_carried() -> None:
    goal = _goal(
        comments=(_comment("UNDATED-RIDER", None), _comment("GARBLED-RIDER", "not a time")),
        claim_at=_CLAIM,
    )

    assert "UNDATED-RIDER" in goal
    assert "GARBLED-RIDER" in goal
    assert "left out" not in goal


def test_the_prior_claim_is_the_newest_ledger_admit_of_this_item(tmp_path: Path) -> None:
    bound = _bound()
    journal = _journal(
        tmp_path,
        [
            {"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": "2026-11-01T00:00:00Z"},
            {"stage": "ledger-admit", "work_item_id": "bd-other", "at": "2026-11-09T00:00:00Z"},
            {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "at": "2026-11-09T01:00:00Z"},
            {"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": "2026-11-05T00:00:00Z"},
        ],
    )

    assert (
        bound.prior_claim_instant(journal_path=journal, item_id=_ITEM_ID) == "2026-11-05T00:00:00Z"
    )  # type: ignore[attr-defined]
    assert bound.prior_claim_instant(journal_path=journal, item_id="bd-never") is None  # type: ignore[attr-defined]
    assert (
        bound.prior_claim_instant(journal_path=tmp_path / "absent.jsonl", item_id=_ITEM_ID) is None
    )  # type: ignore[attr-defined]


def test_the_claim_a_dispatch_takes_does_not_move_its_own_bound(tmp_path: Path) -> None:
    bound = _bound()
    journal = _journal(
        tmp_path,
        [
            {"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": "2026-11-01T00:00:00Z"},
            {
                "stage": "ledger-admit",
                "work_item_id": _ITEM_ID,
                "at": "2026-11-05T00:00:00Z",
                "dispatch_id": "own",
            },
        ],
    )

    own = bound.prior_claim_instant(journal_path=journal, item_id=_ITEM_ID, own_dispatch_id="own")  # type: ignore[attr-defined]
    other = bound.prior_claim_instant(journal_path=journal, item_id=_ITEM_ID, own_dispatch_id="x")  # type: ignore[attr-defined]

    assert own == "2026-11-01T00:00:00Z"
    assert other == "2026-11-05T00:00:00Z"


def _digest(*, bodies: tuple[str, ...], tmp_path: Path) -> str:
    return judgement_subject_digest(item=_item(), cwd=tmp_path, comments=bodies)


def test_a_rider_that_is_not_carried_leaves_the_subject_digest_unchanged(tmp_path: Path) -> None:
    bound = _bound()
    carried = (_comment(_NEW_RIDER, _AFTER), _comment(_STANDING, _BEFORE))
    with_old = (*carried, _comment(_OLD_RIDER, _BEFORE))

    without = bound.carried_comment_bodies(comments=carried, claim_at=_CLAIM)  # type: ignore[attr-defined]
    with_uncarried = bound.carried_comment_bodies(comments=with_old, claim_at=_CLAIM)  # type: ignore[attr-defined]
    with_carried = bound.carried_comment_bodies(  # type: ignore[attr-defined]
        comments=(*carried, _comment("another new one", _AFTER)), claim_at=_CLAIM
    )

    assert _digest(bodies=with_uncarried, tmp_path=tmp_path) == _digest(
        bodies=without, tmp_path=tmp_path
    )
    assert _digest(bodies=with_carried, tmp_path=tmp_path) != _digest(
        bodies=without, tmp_path=tmp_path
    )


def test_carried_bodies_keep_the_receipts_the_reuse_read_needs() -> None:
    bound = _bound()
    receipt = f"{JUDGEMENT_COMMENT_MARKER}\nverdict: passed"

    bodies = bound.carried_comment_bodies(  # type: ignore[attr-defined]
        comments=(_comment(receipt, _BEFORE), _comment(_OLD_RIDER, _BEFORE)), claim_at=_CLAIM
    )

    assert bodies == (receipt,)


def test_the_judgement_comment_reader_drops_uncarried_riders_by_the_repo_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _journal(
        tmp_path,
        [{"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": _CLAIM}],
    )
    comments = (_comment(_OLD_RIDER, _BEFORE), _comment(_NEW_RIDER, _AFTER))
    monkeypatch.setattr(
        _dispatcher_dod_judgement_comments,
        "read_work_item_comments",
        lambda **_kwargs: comments,
    )
    config = StoreConfig(
        tenant="t", prefix="bd-ib", server_user="t", database="t", bd_path="/bin/false", fake=True
    )

    bodies = _dispatcher_dod_judgement_comments.judgement_comment_bodies(
        path=config, work_item_id=_ITEM_ID, repo=tmp_path
    )

    assert bodies == (_NEW_RIDER,)
