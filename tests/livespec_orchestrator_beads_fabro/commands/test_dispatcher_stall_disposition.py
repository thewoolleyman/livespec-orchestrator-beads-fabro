"""Unit-tier cover for the stall-cancel disposition's readings and its arms.

The integration case in `tests/integration/test_dispatcher_stall_cancel_scenario172.py`
asserts the HAPPY release end to end against a live tenant. This module covers
the arms that case cannot reach without breaking the thing it is measuring: a
journal that cannot be read, a line that is not JSON, a row that is not a
mapping, a row whose fields are absent or the wrong type, a terminal that is not
a cancellation at all, and a ledger write that fails.

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    STALL_RELEASE_STAGE,
    UNREAD_CANCEL_ROW,
    dispose_stall_cancel,
    item_stall_cancel_rows,
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


def _outcome(*, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id="01STALLRUN",
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
    assert item_stall_cancel_rows(journal=JournalFile(path=tmp_path), item_id=_ITEM_ID) == ()


def test_a_line_that_is_not_json_yields_no_rows(tmp_path: Path) -> None:
    """A truncated or half-written journal reads as carrying no cancel row.

    Asserted alongside a well-formed row in the SAME file so the case cannot
    pass on a build that returns the empty tuple unconditionally: the
    malformed line is what decides the answer, not the absence of any row.
    """
    journal = _journal(tmp_path=tmp_path, lines=("{not json", _cancel_line(run_id="01A")))
    assert item_stall_cancel_rows(journal=journal, item_id=_ITEM_ID) == ()

    well_formed = _journal(tmp_path=tmp_path / "ok", lines=(_cancel_line(run_id="01A"),))
    assert len(item_stall_cancel_rows(journal=well_formed, item_id=_ITEM_ID)) == 1


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
    rows = item_stall_cancel_rows(journal=journal, item_id=_ITEM_ID)
    assert len(rows) == 1
    assert rows[0].get("run_id") == "01MINE"


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
