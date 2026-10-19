"""Unit-tier cover for the stall-cancel disposition's readings and its arms.

The integration case in `tests/integration/test_dispatcher_stall_cancel_scenario172.py`
asserts the HAPPY release end to end against a live tenant. This module covers
the arms that case cannot reach without breaking the thing it is measuring: a
journal that cannot be read, a line that is not JSON, a row that is not a
mapping, a row whose fields are absent or the wrong type, an `outcome` row no
item can be read off, a terminal that is not a cancellation at all, and a
ledger write that fails.

EVERY ONE OF THOSE ARMS EXISTS TO AVOID A CONFIDENT WRONG ANSWER, which is why
they are asserted rather than left to coverage. An unreadable journal that
raised would strand the item the disposition was about to release; a row whose
`run_id` is null rendered straight into the comment would put the word `None`
where an operator expects a run id; and a failed release that journalled the
success record would report a `ready` item that is still `active`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    UNREAD_CANCEL_ROW,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    STALL_NEEDS_HUMAN_STAGE,
    STALL_RELEASE_HELD_STAGE,
    STALL_RELEASE_STAGE,
    consecutive_stall_cancel_rows,
    dispose_stall_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-stalldisp"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice the watchdog cancelled",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-12T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _outcome(*, status: str, factory_name: str | None = None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id="01STALLRUN",
        fabro_factory_name=factory_name,
    )


def _journal(*, tmp_path: Path, lines: tuple[str, ...] = ()) -> JournalFile:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return JournalFile(path=path)


def _cancel_line(**fields: object) -> str:
    record: dict[str, object] = {
        "stage": "watchdog-stall-cancel",
        "work_item_id": _ITEM_ID,
    }
    record.update(fields)
    return json.dumps(record)


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def test_an_unreadable_journal_yields_no_rows_rather_than_raising(tmp_path: Path) -> None:
    """A journal the dispatch cannot read is an absence, never an exception.

    The terminal is already final by the time the disposition runs, so a read
    that raised would strand the item it was about to release — the exact end
    state this routing exists to retire. `tmp_path` itself is passed as the
    journal path so the read fails as a directory read rather than through a
    monkeypatched builtin, which would also pass on a build that caught the
    wrong exception.
    """
    assert consecutive_stall_cancel_rows(journal=JournalFile(path=tmp_path), item_id=_ITEM_ID) == ()


def test_a_line_that_is_not_json_yields_no_rows(tmp_path: Path) -> None:
    """A truncated or half-written journal reads as carrying no cancel row.

    Asserted alongside a well-formed row in the SAME file so the case cannot
    pass on a build that returns the empty tuple unconditionally: the
    malformed line is what decides the answer, not the absence of any row.
    """
    journal = _journal(tmp_path=tmp_path, lines=("{not json", _cancel_line(run_id="01A")))
    assert consecutive_stall_cancel_rows(journal=journal, item_id=_ITEM_ID) == ()

    well_formed = _journal(tmp_path=tmp_path / "ok", lines=(_cancel_line(run_id="01A"),))
    assert len(consecutive_stall_cancel_rows(journal=well_formed, item_id=_ITEM_ID)) == 1


def test_only_this_items_cancel_rows_are_returned(tmp_path: Path) -> None:
    """A row is this item's cancel row only if BOTH its stage and its id match.

    Both halves are asserted because either alone would pass a build that
    dropped the other check, and each failure is wrong in a different
    direction: dropping the stage test counts an unrelated record as a
    cancellation, while dropping the id test attributes another item's
    cancellation to this one.
    """
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            json.dumps(["not", "a", "mapping"]),
            json.dumps({"stage": "watchdog-stall-cancel", "work_item_id": "bd-ib-other"}),
            json.dumps({"stage": "non-convergence-bounce", "work_item_id": _ITEM_ID}),
            _cancel_line(run_id="01MINE"),
        ),
    )
    rows = consecutive_stall_cancel_rows(journal=journal, item_id=_ITEM_ID)
    assert len(rows) == 1
    assert rows[0].get("run_id") == "01MINE"


def _terminal_line(**outcome: object) -> str:
    """One `outcome` journal row, nesting the terminal exactly as the dispatch does."""
    return json.dumps({"stage": "outcome", "outcome": outcome})


def test_a_terminal_row_this_item_cannot_be_read_off_leaves_the_run_unbroken(
    tmp_path: Path,
) -> None:
    """An unattributable terminal cuts nothing, because it is about nobody.

    Two shapes reach the same answer and both are asserted, because they fail
    at different readings and a build dropping either one would still pass the
    other: an `outcome` key holding something that is not a mapping, which no
    `work_item_id` can be read out of at all, and a well-formed terminal
    belonging to ANOTHER item. Neither says anything about this item, so
    neither may end its run of cancellations — a build treating an unreadable
    or foreign terminal as a reset would release a genuinely repeat
    cancellation back to the queue, which is the unbounded loop with no
    operator in it that the needs-human arm exists to stop.

    This is the opposite direction from a terminal that IS this item's but
    whose status cannot be read as the stall status, which DOES cut the run;
    the integration module asserts that half against the live tenant. The two
    together are the reading's whole discrimination, and asserting only one
    leaves the other free to be inverted.
    """
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _cancel_line(run_id="01FIRST"),
            json.dumps({"stage": "outcome", "outcome": "not a mapping"}),
            _terminal_line(work_item_id="bd-ib-other", status="green"),
            _cancel_line(run_id="01SECOND"),
        ),
    )

    rows = consecutive_stall_cancel_rows(journal=journal, item_id=_ITEM_ID)

    assert [row.get("run_id") for row in rows] == ["01FIRST", "01SECOND"]


def test_this_items_own_non_stall_terminal_cuts_the_run(tmp_path: Path) -> None:
    """The reset is the LAST such terminal, and only cancellations after it count.

    Three cancellations straddling two of this item's terminals: the run is cut
    at the later one, so a build reading the FIRST reset — or reading any reset
    at all rather than the last — reports two consecutive cancellations where
    one stands, and parks an item the clause says to release. The stall-status
    terminal between them is the control that the cut keys on the status: it
    sits after a cancellation and must leave the run unbroken.
    """
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _cancel_line(run_id="01FIRST"),
            _terminal_line(work_item_id=_ITEM_ID, status="stalled-no-progress"),
            _terminal_line(work_item_id=_ITEM_ID, status="blocked"),
            _cancel_line(run_id="01SECOND"),
            _terminal_line(work_item_id=_ITEM_ID, status="failed"),
            _cancel_line(run_id="01THIRD"),
        ),
    )

    rows = consecutive_stall_cancel_rows(journal=journal, item_id=_ITEM_ID)

    assert [row.get("run_id") for row in rows] == ["01THIRD"]


def test_a_terminal_that_is_not_a_cancellation_is_left_alone(tmp_path: Path) -> None:
    """Every non-stall terminal passes through untouched.

    `failed` is the discriminating status rather than `green`: a green run has
    already been completed and accepted by the time this runs, so a build that
    keyed on "not green" would still leave this case correct while releasing
    every ordinary failure back to `ready` — undoing the needs-human park that
    owns it.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    dispose_stall_cancel(
        repo=repo, item=_item(), outcome=_outcome(status="failed"), journal=journal
    )

    assert materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status == (
        "active"
    )
    assert _stages(journal=journal) == []
    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()


def test_an_external_fabro_cancel_blocks_the_item_and_names_its_run_and_factory(
    tmp_path: Path,
) -> None:
    """An operator cancellation rests for a human, unlike the watchdog status."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    dispose_terminal_routing(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="cancelled", factory_name="hp"),
        journal=journal,
        now_iso="2026-10-19T03:22:00Z",
    )

    blocked = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert blocked.status == "blocked"
    assert blocked.blocked_reason == "needs-human"
    comment = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    assert "01STALLRUN" in comment
    assert "hp" in comment


def test_fields_the_cancel_row_does_not_carry_are_stated_as_unread(tmp_path: Path) -> None:
    """A null, a non-string and a blank field each report the failed reading.

    All three collapse onto one statement because they are one finding — this
    dispatch's journal does not say — while rendering the raw value would put
    `None`, a number, or nothing at all where an operator expects a run id. The
    comment is read back from the TENANT rather than from the renderer, so the
    case also proves the body reached the ledger.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        lines=(_cancel_line(run_id=None, factory=7, executing_stage="   "),),
    )
    append_work_item(path=_config(), item=_item())

    dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    body = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    assert body.count(UNREAD_CANCEL_ROW) == 3
    assert "None" not in body
    assert STALL_RELEASE_STAGE in _stages(journal=journal)


def test_a_cancel_with_no_journalled_row_still_releases_the_claim(tmp_path: Path) -> None:
    """An interrupted dispatch that journalled no cancel row still releases.

    The claim release is what un-strands the item, so it must not be
    conditional on the account being readable: a disposition that refused to
    release because it could not name the run would leave the item `active`
    for exactly the dispatches most likely to have been interrupted. The
    comment states the absent reading instead.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    released = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert released.status == "ready"
    assert released.assignee is None
    assert (
        UNREAD_CANCEL_ROW in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    )


def test_a_failed_release_journals_the_error_and_not_the_success(tmp_path: Path) -> None:
    """A ledger write that could not land reports the failure it hit.

    The item is deliberately NOT filed in the tenant, so the release raises
    `WorkItemNotFoundError` — the pruned-between-dispatch-and-disposition case
    the fail-soft exists for. The success record's ABSENCE is asserted beside
    the error record's presence because a build that appended both would
    report a `ready` item that is still `active`, which is the one reading an
    operator acts on.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, lines=(_cancel_line(run_id="01GONE"),))

    dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    stages = _stages(journal=journal)
    assert f"{STALL_RELEASE_STAGE}-error" in stages
    assert STALL_RELEASE_STAGE not in stages


def test_a_failed_rest_journals_the_error_and_not_the_success(tmp_path: Path) -> None:
    """The repeat-cancellation arm fails soft in the same shape the release does.

    Two cancel rows route to the needs-human disposition, and the item is again
    deliberately absent from the tenant so the blocked write raises. The pair of
    assertions mirrors the release case for the same reason: a build appending
    the success record would report an item resting at `blocked` / `needs-human`
    that is in fact still `active` and still claimed, which is the reading that
    decides whether an operator goes looking for it.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        lines=(_cancel_line(run_id="01FIRSTGONE"), _cancel_line(run_id="01SECONDGONE")),
    )

    dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    stages = _stages(journal=journal)
    assert f"{STALL_NEEDS_HUMAN_STAGE}-error" in stages
    assert STALL_NEEDS_HUMAN_STAGE not in stages


def test_an_interrupted_release_is_held_rather_than_stealing_a_newer_claim(
    tmp_path: Path,
) -> None:
    """The replay arm whose release had NOT landed before a newer dispatch claimed.

    This is the sharp half of the replay rule, and it is a different mechanism
    from the already-released hold its integration sibling exercises. There a
    release row stands, so the replay owes nothing; here the interrupted
    dispatch died BEFORE writing one, so a release genuinely is owed — and
    taking it now would clear the assignee of the run the ordinary admission
    valve has since started, leaving a row an operator reads as a healthy
    first release while two runs publish onto one branch.

    The reason is asserted rather than merely the hold, because the two hold
    reasons have opposite consequences: `already-released` says the work is
    complete, while this one says it is still outstanding and a human or a
    later pass must finish it once the live dispatch ends.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _cancel_line(run_id="01STALLRUN", factory="hp"),
            json.dumps(
                {
                    "stage": "dispatch-id",
                    "work_item_id": _ITEM_ID,
                    "dispatch_id": "0000000000000000000000000000beef",
                }
            ),
        ),
    )

    dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    held = [record for record in records if record.get("stage") == STALL_RELEASE_HELD_STAGE]
    assert len(held) == 1
    assert held[0]["reason"] == "newer-dispatch-claim"
    assert STALL_RELEASE_STAGE not in [record.get("stage") for record in records]
