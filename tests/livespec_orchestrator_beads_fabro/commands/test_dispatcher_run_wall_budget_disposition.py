"""Where a wall-budget cancel leaves its work-item (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "After a budget cancel the Dispatcher MUST rest the item
at `blocked` with `blocked_reason` `needs-human`. Its ledger comment MUST name
the run id, the factory, the stage, the elapsed seconds, the budget, the
preserve-by-reference pointer and, when the record names them, the pull request
and the published head, and MUST name the remedy `resolve-blocked:<id>:ready`."

A BUDGET CANCEL NEVER RELEASES, which is the one way it differs from the stall
cancel's first arm: a stall says nothing about the slice, so the slice goes back
to the queue, while a run that spent six hours of slot without finishing is a
decision a person has to take. Nothing automatic leaves that state, which is
also why the comment has to carry the way out.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    UNREAD_CANCEL_ROW,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_disposition"
_ITEM_ID = "bd-ib-budgetdisp"
_RUN_ID = "01BUDGETRUN"
_POINTER = "comment-9173"
_NOW_ISO = "2026-10-13T18:00:00Z"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module_path() -> Path:
    """Where the budget disposition lives, beside the budget it disposes of."""
    return Path(str(_node_timeouts.__file__)).with_name(
        "_dispatcher_run_wall_budget_disposition.py"
    )


def _disposition() -> Any:
    """The disposition module, imported inside a test body rather than at top."""
    assert _module_path().is_file(), f"{_module_path()} does not exist"
    return importlib.import_module(_MODULE)


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


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice that outran its wall budget",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _outcome(*, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN_ID,
    )


def _journal(*, tmp_path: Path, lines: tuple[str, ...]) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return JournalFile(path=path)


def _exceeded_line(**overrides: object) -> str:
    record: dict[str, object] = {
        "stage": RUN_WALL_BUDGET_EXCEEDED_STAGE,
        "work_item_id": _ITEM_ID,
        "run_id": _RUN_ID,
        "factory": "hp",
        "executing_stage": "implement",
        "elapsed_seconds": 25200.0,
        "budget_seconds": 21600.0,
        "budget_layer": "repository",
        "preserved_pointer": _POINTER,
    }
    record.update(overrides)
    return json.dumps(record)


def _dispose(*, tmp_path: Path, lines: tuple[str, ...], status: str) -> tuple[Path, JournalFile]:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path, lines=lines)
    _disposition().dispose_run_wall_budget_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status=status),
        journal=journal,
    )
    return repo, journal


def _only(*, item_id: str) -> WorkItem:
    items = [item for item in read_work_items(path=_config()) if item.id == item_id]
    return items[-1]


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def test_a_budget_cancel_rests_the_item_at_blocked_needs_human(tmp_path: Path) -> None:
    """The item leaves `active` for `blocked` / `needs-human`, admission manual."""
    disposition = _disposition()
    _, journal = _dispose(
        tmp_path=tmp_path,
        lines=(_exceeded_line(),),
        status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
    )
    rested = _only(item_id=_ITEM_ID)
    assert rested.status == "blocked"
    assert rested.blocked_reason == "needs-human"
    # `blocked` alone is a status a drain could be configured to admit, so the
    # policy rides the same write for the reason the stall terminal's does.
    assert rested.admission_policy == "manual"
    assert disposition.RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE in _stages(journal=journal)


def test_the_comment_names_the_run_the_measurement_and_the_way_out(tmp_path: Path) -> None:
    """Every fact the clause enumerates, plus the remedy, in one durable comment."""
    _ = _dispose(
        tmp_path=tmp_path,
        lines=(_exceeded_line(),),
        status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
    )
    bodies = [
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    ]
    assert len(bodies) == 1
    body = bodies[0]
    assert _RUN_ID in body
    assert "hp" in body
    assert "implement" in body
    assert "25200" in body
    assert "21600" in body
    assert _POINTER in body
    assert f"resolve-blocked:{_ITEM_ID}:ready" in body


def test_an_unread_fact_is_stated_rather_than_rendered_as_a_null(tmp_path: Path) -> None:
    """A journal row carrying no run id says so instead of printing `None`.

    An omission is what a record written by a build predating this reading looks
    like, so a comment that simply left the run unnamed would be
    indistinguishable from one whose row could not be found.
    """
    _ = _dispose(
        tmp_path=tmp_path,
        lines=(_exceeded_line(run_id=None, preserved_pointer=None),),
        status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
    )
    body = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    assert UNREAD_CANCEL_ROW in body
    assert "None" not in body


def test_a_journal_with_no_exceeded_row_still_rests_the_item(tmp_path: Path) -> None:
    """A lost record costs the comment its facts, never the item its rest state.

    An interrupted dispatch can end between the cancel and the disposition, and
    those are exactly the dispatches most likely to have left a slot-holding run
    behind -- so the rest state does not depend on the journal being readable.
    """
    _, journal = _dispose(tmp_path=tmp_path, lines=(), status=RUN_WALL_BUDGET_EXCEEDED_STAGE)
    assert _only(item_id=_ITEM_ID).status == "blocked"
    body = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    assert UNREAD_CANCEL_ROW in body
    assert _stages(journal=journal) == [_disposition().RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE]


def test_the_newest_exceeded_row_is_the_one_reported(tmp_path: Path) -> None:
    """A re-dispatched item reports THIS cancel, never an earlier one's run."""
    _ = _dispose(
        tmp_path=tmp_path,
        lines=(
            _exceeded_line(run_id="01EARLIERRUN", preserved_pointer="comment-1"),
            _exceeded_line(),
        ),
        status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
    )
    body = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    assert _RUN_ID in body
    assert "01EARLIERRUN" not in body


def test_every_other_terminal_is_left_alone(tmp_path: Path) -> None:
    """A no-op for every outcome that is not a budget cancel."""
    repo, journal = _dispose(tmp_path=tmp_path, lines=(_exceeded_line(),), status="green")
    _ = repo
    assert _only(item_id=_ITEM_ID).status == "active"
    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()
    assert _stages(journal=journal) == [RUN_WALL_BUDGET_EXCEEDED_STAGE]


def test_the_terminal_router_runs_the_budget_disposition(tmp_path: Path) -> None:
    """The route is declared beside its peers rather than left to a caller.

    Keeping every non-green terminal's disposition in one place is what lets a
    reader see that no terminal is left with no disposition at all -- and a
    budget cancel reaching the router with no arm of its own would rest
    `active` with `fabro` still assigned and no run behind it.
    """
    disposition = _disposition()
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path, lines=(_exceeded_line(),))
    dispose_terminal_routing(
        repo=repo,
        item=_item(),
        outcome=_outcome(status=RUN_WALL_BUDGET_EXCEEDED_STAGE),
        journal=journal,
        now_iso=_NOW_ISO,
    )
    assert _only(item_id=_ITEM_ID).status == "blocked"
    assert disposition.RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE in _stages(journal=journal)


def test_a_failed_ledger_write_journals_its_own_error_stage(tmp_path: Path) -> None:
    """A rest that could not be written says so rather than reporting success."""
    disposition = _disposition()
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, lines=(_exceeded_line(),))
    # The item is deliberately NOT appended to the tenant, so the blocked-state
    # write refuses with the not-found error the disposition is fail-soft over.
    disposition.dispose_run_wall_budget_cancel(
        repo=repo,
        item=replace(_item(), id="bd-ib-neverfiled"),
        outcome=_outcome(status=RUN_WALL_BUDGET_EXCEEDED_STAGE),
        journal=journal,
    )
    stages = _stages(journal=journal)
    assert f"{disposition.RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE}-error" in stages
    assert disposition.RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE not in stages
