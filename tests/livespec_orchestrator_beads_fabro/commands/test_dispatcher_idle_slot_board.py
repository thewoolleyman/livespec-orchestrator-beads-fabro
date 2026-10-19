"""Coverage for the idle-slot board reading: live, queued, and attribution.

The `submitted` row in the fixture is not decoration. The clause rules it
neither live nor queued, and the only way that is visible is by putting one on
the board beside the rows that do count.
"""

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_idle_slot_board.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"


def _run(*, run_id: str, status: str, work_item: str | None = None) -> FabroRunSummary:
    goal = None if work_item is None else f"Work-item: {work_item}\nGoal text.\n"
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status,
        goal=goal,
        total_usd_micros=None,
        work_item_id=work_item,
    )


class _Lister:
    """A `RunLister` double: one canned answer, and the factory it was asked."""

    def __init__(self, *, runs: tuple[FabroRunSummary, ...] | None) -> None:
        self._runs = runs
        self.asked: list[str] = []

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
        self.asked.append(factory)
        return self._runs


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def test_a_readable_board_counts_live_and_queued_rows_and_attributes_them() -> None:
    """Live is non-terminal, queued is `runnable`, `submitted` is neither."""
    assert _MODULE_PATH.is_file()
    module = _module()
    lister = _Lister(
        runs=(
            _run(run_id="r1", status="running", work_item="bd-running"),
            _run(run_id="r2", status="runnable", work_item="bd-queued"),
            _run(run_id="r3", status="blocked", work_item="bd-blocked"),
            _run(run_id="r4", status="succeeded", work_item="bd-done"),
            _run(run_id="r5", status="submitted", work_item="bd-submitted"),
            _run(run_id="r6", status="running"),
        ),
    )

    reading = module.read_idle_slot_board(repo=Path("/repo"), factory="hp", lister=lister)

    assert lister.asked == ["hp"]
    assert reading.observable is True
    assert reading.live_count == 4
    assert reading.queued_count == 1
    assert reading.live_item_ids == frozenset({"bd-running", "bd-queued", "bd-blocked"})


def test_an_unreadable_board_is_unobservable_with_unknown_counts() -> None:
    """Both counts stay `None`: a zero is the one reading that fires a finding."""
    assert _MODULE_PATH.is_file()
    module = _module()

    reading = module.read_idle_slot_board(
        repo=Path("/repo"), factory="hp", lister=_Lister(runs=None)
    )

    assert reading == module.UNOBSERVABLE_BOARD
    assert reading.observable is False
    assert reading.live_count is None
    assert reading.queued_count is None
    assert reading.live_item_ids == frozenset()


def test_the_default_lister_is_the_declared_factory_run_reader() -> None:
    """With no injected lister the reader resolves the repo's own factories."""
    assert _MODULE_PATH.is_file()
    module = _module()

    reading = module.read_idle_slot_board(repo=Path("/nonexistent-repo"), factory="absent")

    assert reading.observable is False


def test_board_reading_over_an_empty_listing_is_an_observable_empty_board() -> None:
    """An empty board is OBSERVABLE with two zeros — not an absent reading."""
    assert _MODULE_PATH.is_file()
    module = _module()

    reading = module.board_reading(runs=())

    assert (reading.observable, reading.live_count, reading.queued_count) == (True, 0, 0)
