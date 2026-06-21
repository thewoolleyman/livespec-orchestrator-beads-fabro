"""Per-wrapper coverage test for bin/orchestrator.py."""

from collections.abc import Callable


def test_orchestrator_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "orchestrator.py",
        "livespec_orchestrator_beads_fabro.commands.orchestrator",
        0,
    )
