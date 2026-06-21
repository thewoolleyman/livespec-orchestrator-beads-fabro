"""Per-wrapper coverage test for bin/dispatcher.py."""

from collections.abc import Callable


def test_dispatcher_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "dispatcher.py",
        "livespec_orchestrator_beads_fabro.commands.dispatcher",
        0,
    )
