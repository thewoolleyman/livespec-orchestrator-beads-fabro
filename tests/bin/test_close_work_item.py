"""Per-wrapper coverage test for bin/close_work_item.py."""

from collections.abc import Callable


def test_close_work_item_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "close_work_item.py",
        "livespec_orchestrator_beads_fabro.commands.close_work_item",
        0,
    )
