"""How the bounded rider set (bd-ib-l2poch) reaches a real dispatch.

`test_dispatcher_rider_bound` covers the rule on its own. These cases cover the
seams a rule can be correct at and still never reach a dispatch: the admission
row that records the claim, the two call sites that bound the goal and the
in-run subject by it, and the lock resolution that keeps the dispatch's id equal
to the id its claim was journaled under. Each wiring case reads the PARSED source
rather than matching text, for the reason `test_dispatcher_goal_recovery` gives:
`render_goal`'s `claim_at` defaults to absent, so a call site that dropped it
would render every rider and say nothing about it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_judgement_comments,
    _dispatcher_loop_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import (
    DispatchLaunchContext,
    dispatch_lock_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound import (
    bound_riders,
    carried_comment_bodies,
    claim_journal_record,
    left_out_line,
    prior_claim_instant,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import WorkItemComment, append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-wired"
_LOOP = Path(_dispatcher_loop_overlay.__file__).with_name("_dispatcher_loop.py")
_OVERLAY = Path(_dispatcher_loop_overlay.__file__)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A slice whose claim is journaled",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _calls(*, path: Path, name: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]


def _keyword(*, call: ast.Call, name: str) -> ast.expr:
    [bound] = [kw.value for kw in call.keywords if kw.arg == name]
    return bound


def test_admission_journals_the_claim_under_the_dispatch_id_the_lock_carries(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "tmp" / "journal.jsonl")
    item = _item()
    append_work_item(path=_config(), item=item)

    admission = admit_and_select(
        repo=repo, items=[item], candidates=[item], journal=journal, enforce_cap=False
    )

    [claim] = [
        record
        for record in map(json.loads, journal.path.read_text(encoding="utf-8").splitlines())
        if record["stage"] == "ledger-admit"
    ]
    assert [admitted.id for admitted in admission.admitted] == [_ITEM_ID]
    lock = live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID)
    assert claim["dispatch_id"]
    assert lock is not None
    assert lock.dispatch_id == claim["dispatch_id"]
    assert prior_claim_instant(journal_path=journal.path, item_id=_ITEM_ID) == claim["at"]
    assert (
        prior_claim_instant(
            journal_path=journal.path, item_id=_ITEM_ID, own_dispatch_id=claim["dispatch_id"]
        )
        is None
    )


def test_the_dispatch_lock_hands_its_id_on_and_a_bare_launch_mints_one(tmp_path: Path) -> None:
    minted = iter(("minted-1", "minted-2"))

    bare_id, bare_path = dispatch_lock_for(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        context=DispatchLaunchContext(),
        mint_id=lambda: next(minted),
    )
    inherited_id, inherited_path = dispatch_lock_for(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        context=DispatchLaunchContext(),
        mint_id=lambda: next(minted),
    )
    release_dispatch_lock(path=bare_path)
    admitted = write_dispatch_lock(
        repo=tmp_path, work_item_id="bd-ib-other", dispatch_id="from-admit"
    )
    adopted_id, adopted_path = dispatch_lock_for(
        repo=tmp_path,
        work_item_id="bd-ib-other",
        context=DispatchLaunchContext(),
        mint_id=lambda: "never-used",
    )

    assert bare_id == "minted-1"
    assert (inherited_id, inherited_path) == ("minted-1", bare_path)
    assert (adopted_id, adopted_path) == ("from-admit", admitted)
    assert next(minted) == "minted-2"


def test_the_dispatch_path_bounds_its_goal_at_the_claim_it_follows() -> None:
    [render] = _calls(path=_LOOP, name="render_goal")

    bound = _keyword(call=render, name="claim_at")

    assert isinstance(bound, ast.Call)
    assert isinstance(bound.func, ast.Name)
    assert bound.func.id == "prior_claim_instant"
    assert {kw.arg for kw in bound.keywords} == {"journal_path", "item_id", "own_dispatch_id"}


def test_the_in_run_subject_is_computed_over_the_same_carried_bodies() -> None:
    [subject] = _calls(path=_OVERLAY, name="dod_gate_subject")

    comments = _keyword(call=subject, name="comments")

    assert isinstance(comments, ast.Call)
    assert isinstance(comments.func, ast.Name)
    assert comments.func.id == "carried_comment_bodies"
    [claim] = [kw.value for kw in comments.keywords if kw.arg == "claim_at"]
    assert isinstance(claim, ast.Call)
    assert {kw.arg for kw in claim.keywords} == {"journal_path", "item_id", "own_dispatch_id"}


def _comment(text: str, created_at: str | None) -> WorkItemComment:
    return WorkItemComment(text=text, author=None, created_at=created_at)


def test_a_rider_created_at_the_claim_instant_is_carried_and_a_zone_less_time_is_read_as_utc() -> (
    None
):
    riders = bound_riders(
        comments=(
            _comment("AT-THE-CLAIM", "2026-11-10T06:00:00Z"),
            _comment("ZONELESS-BEFORE", "2026-11-10T05:59:59"),
            _comment("OFFSET-AFTER", "2026-11-10T08:00:01+02:00"),
        ),
        claim_at="2026-11-10T06:00:00Z",
    )

    assert [comment.text for comment in riders.carried] == ["AT-THE-CLAIM", "OFFSET-AFTER"]
    assert riders.left_out == 1
    assert riders.left_out_newest_at == "2026-11-10T05:59:59"


def test_only_a_well_formed_stage_scope_on_the_first_line_carries_an_old_rider() -> None:
    old = "2026-11-01T00:00:00Z"
    riders = bound_riders(
        comments=(
            _comment("\n\nFOR implement ONLY: tighten.", old),
            _comment("FOR implement, review_fix ONLY:\nbody", old),
            _comment("FOR ONLY: nothing named", old),
            _comment("body first\nFOR implement ONLY:", old),
            _comment("for implement only: lowercase", old),
            _comment("STANDING RIDERS: wrong prefix", old),
        ),
        claim_at="2026-11-10T06:00:00Z",
    )

    assert [comment.text.strip().splitlines()[0] for comment in riders.carried] == [
        "FOR implement ONLY: tighten.",
        "FOR implement, review_fix ONLY:",
    ]
    assert riders.left_out == 4


def test_a_journal_row_without_a_readable_instant_bounds_nothing(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": "2026-11-02T00:00:00Z"},
                {"stage": "ledger-admit", "work_item_id": _ITEM_ID, "at": "garbled"},
                {"stage": "ledger-admit", "work_item_id": _ITEM_ID},
            )
        ),
        encoding="utf-8",
    )

    assert prior_claim_instant(journal_path=journal, item_id=_ITEM_ID) == "2026-11-02T00:00:00Z"


def test_carried_bodies_with_no_claim_keep_every_rider() -> None:
    bodies = carried_comment_bodies(
        comments=(_comment("one", "2026-11-01T00:00:00Z"), _comment("two", None)), claim_at=None
    )

    assert bodies == ("one", "two")


def test_a_set_that_left_nothing_out_states_no_line_and_the_claim_row_names_its_fields() -> None:
    nothing_left_out = bound_riders(
        comments=(_comment("new", "2026-11-11T00:00:00Z"),), claim_at="x"
    )

    assert left_out_line(item_id=_ITEM_ID, riders=nothing_left_out) == ""
    assert claim_journal_record(item_id=_ITEM_ID, assignee="fabro", dispatch_id="d1") == {
        "stage": "ledger-admit",
        "work_item_id": _ITEM_ID,
        "assignee": "fabro",
        "dispatch_id": "d1",
    }


def test_an_unreadable_ledger_leaves_the_judgement_comments_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _unreadable(**_kwargs: object) -> tuple[WorkItemComment, ...]:
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="down")

    monkeypatch.setattr(_dispatcher_dod_judgement_comments, "read_work_item_comments", _unreadable)

    assert (
        _dispatcher_dod_judgement_comments.judgement_comment_bodies(
            path=_config(), work_item_id=_ITEM_ID, repo=tmp_path
        )
        is None
    )
