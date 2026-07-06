"""Per-wrapper coverage test for bin/list_plan_threads.py."""

from collections.abc import Callable


def test_list_plan_threads_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "list_plan_threads.py",
        "livespec_orchestrator_beads_fabro.commands.list_plan_threads",
        0,
    )
