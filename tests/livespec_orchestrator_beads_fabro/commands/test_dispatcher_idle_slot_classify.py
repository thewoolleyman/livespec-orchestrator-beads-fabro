"""Coverage for the idle-slot classifier: exactly one class, blockers shown.

The subject is the clause's own ladder, so the table-driven case below is the
whole assertion rather than a convenience: every non-closed status must land on
exactly one of the twelve declared classes, and a status the vocabulary does
not know must land on `UNCLASSIFIED-STATUS` naming itself rather than on a
plausible neighbour.
"""

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_PATH = _COMMANDS / "_dispatcher_idle_slot_classify.py"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify"
_BOARD_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title=f"{id_} title",
        description="A description with no workflow scope in it.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _local(*, blocker_id: str) -> dict[str, str]:
    return {"kind": "local", "work_item_id": blocker_id}


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _empty_board() -> object:
    return importlib.import_module(_BOARD_NAME).UNOBSERVABLE_BOARD


def _classify(**kwargs: object) -> object:
    return _module().classify_child(**kwargs)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("active", "POST-RUN"),
        ("in_progress", "POST-RUN"),
        ("acceptance", "NEEDS-CAPTURE-OR-ACCEPT"),
        ("pending-approval", "NEEDS-APPROVAL"),
        ("backlog", "UNADMITTED"),
        ("open", "UNADMITTED"),
        ("blocked", "PARKED"),
        ("deferred", "PARKED"),
        ("ready", "DISPATCHABLE-NOW"),
    ],
)
def test_every_status_lands_on_exactly_one_declared_class(status: str, expected: str) -> None:
    """The status ladder, end to end, against the declared class vocabulary."""
    assert _MODULE_PATH.is_file()
    module = _module()

    classified = _classify(
        item=_item(id_="bd-one", status=status),
        blockers=(),
        board=_empty_board(),
        hold_reasons={},
    )

    assert classified.classification == expected
    assert classified.classification in module.IDLE_SLOT_CLASSES
    assert classified.id == "bd-one"
    assert classified.status == status


def test_an_unknown_status_is_unclassified_and_names_itself() -> None:
    """A status outside the vocabulary never borrows a plausible neighbour."""
    assert _MODULE_PATH.is_file()
    module = _module()

    classified = _classify(
        item=_item(id_="bd-odd", status="marinating"),
        blockers=(),
        board=_empty_board(),
        hold_reasons={},
    )

    assert classified.classification == module.CLASS_UNCLASSIFIED_STATUS
    assert classified.reason == "marinating"


def test_a_ready_child_with_an_open_blocker_is_blocked_and_shows_it() -> None:
    """The blockers ride on the classified row, with the statuses shown."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(id_="bd-child", depends_on=(_local(blocker_id="bd-blocker"),))

    blockers = module.open_blockers(item=item, statuses={"bd-blocker": "backlog"})
    classified = _classify(item=item, blockers=blockers, board=_empty_board(), hold_reasons={})

    assert classified.classification == module.CLASS_BLOCKED
    assert [(blocker.id, blocker.status) for blocker in classified.blockers] == [
        ("bd-blocker", "backlog")
    ]


def test_a_host_only_ready_child_is_host_only_before_any_blocker_is_read() -> None:
    """`HOST-ONLY` precedes the blocker arms, exactly as the ladder orders it."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(
        id_="bd-host",
        factory_safety="needs the host credential",
        depends_on=(_local(blocker_id="bd-blocker"),),
    )

    classified = _classify(
        item=item,
        blockers=module.open_blockers(item=item, statuses={"bd-blocker": "backlog"}),
        board=_empty_board(),
        hold_reasons={},
    )

    assert classified.classification == module.CLASS_HOST_ONLY


def test_a_child_with_an_attributed_live_row_is_running_whatever_its_status() -> None:
    """`RUNNING` is the first rule, so it outranks every status arm below it."""
    assert _MODULE_PATH.is_file()
    module = _module()
    board = importlib.import_module(_BOARD_NAME).BoardReading(
        observable=True,
        live_count=1,
        queued_count=0,
        live_item_ids=frozenset({"bd-live"}),
    )

    classified = _classify(
        item=_item(id_="bd-live", status="backlog"),
        blockers=(),
        board=board,
        hold_reasons={},
    )

    assert classified.classification == module.CLASS_RUNNING


def test_open_blockers_drops_closed_ones_and_reports_an_absent_one_unresolved() -> None:
    """A closed blocker is not open; a blocker absent from the tenant is."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(
        id_="bd-child",
        depends_on=(
            _local(blocker_id="bd-closed"),
            _local(blocker_id="bd-gone"),
            "bd-bare",
            {"kind": "pull_request", "repo": "r", "number": 1},
        ),
    )

    blockers = module.open_blockers(item=item, statuses={"bd-closed": "closed", "bd-bare": "ready"})

    assert [(blocker.id, blocker.status) for blocker in blockers] == [
        ("bd-bare", "ready"),
        ("bd-gone", module.BLOCKER_STATUS_ABSENT),
    ]


def _board_with(*, live_ids: frozenset[str]) -> object:
    return importlib.import_module(_BOARD_NAME).BoardReading(
        observable=True, live_count=len(live_ids), queued_count=0, live_item_ids=live_ids
    )


def test_an_active_blocker_with_a_live_row_blocks_and_without_one_is_a_stale_edge() -> None:
    """`active` means in flight, not landed — the measured pe2dxk correction."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(id_="bd-dependent", depends_on=(_local(blocker_id="bd-blocker"),))
    blockers = module.open_blockers(item=item, statuses={"bd-blocker": "active"})

    with_run = _classify(
        item=item,
        blockers=blockers,
        board=_board_with(live_ids=frozenset({"bd-blocker"})),
        hold_reasons={},
    )
    without_run = _classify(
        item=item, blockers=blockers, board=_board_with(live_ids=frozenset()), hold_reasons={}
    )

    assert with_run.classification == module.CLASS_BLOCKED
    assert without_run.classification == module.CLASS_STALE_EDGE


def test_an_acceptance_blocker_is_a_stale_edge_whatever_the_board_says() -> None:
    """An `acceptance` blocker has landed and was never closed, run or no run."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(id_="bd-dependent", depends_on=(_local(blocker_id="bd-landed"),))

    classified = _classify(
        item=item,
        blockers=module.open_blockers(item=item, statuses={"bd-landed": "acceptance"}),
        board=_board_with(live_ids=frozenset({"bd-landed"})),
        hold_reasons={},
    )

    assert classified.classification == module.CLASS_STALE_EDGE


def test_one_real_blocker_beside_a_stale_edge_still_blocks() -> None:
    """STALE-EDGE requires EVERY open blocker to be a landed-but-unclosed edge."""
    assert _MODULE_PATH.is_file()
    module = _module()
    item = _item(
        id_="bd-dependent",
        depends_on=(_local(blocker_id="bd-landed"), _local(blocker_id="bd-open")),
    )

    classified = _classify(
        item=item,
        blockers=module.open_blockers(
            item=item, statuses={"bd-landed": "acceptance", "bd-open": "ready"}
        ),
        board=_board_with(live_ids=frozenset()),
        hold_reasons={},
    )

    assert classified.classification == module.CLASS_BLOCKED


def test_a_ready_child_the_verdict_does_not_admit_is_held_with_its_reason() -> None:
    """The reason rides beside the class, so the row says WHY nothing moves."""
    assert _MODULE_PATH.is_file()
    module = _module()

    classified = _classify(
        item=_item(id_="bd-held"),
        blockers=(),
        board=_empty_board(),
        hold_reasons={"bd-held": "refused at the readiness stage"},
    )

    assert classified.classification == module.CLASS_HELD
    assert classified.reason == "refused at the readiness stage"
