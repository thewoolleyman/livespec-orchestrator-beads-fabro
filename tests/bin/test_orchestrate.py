"""Per-wrapper coverage test for bin/orchestrate.py."""

from collections.abc import Callable


def test_orchestrate_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "orchestrate.py",
        "livespec_orchestrator_beads_fabro.commands.orchestrate",
        0,
    )
