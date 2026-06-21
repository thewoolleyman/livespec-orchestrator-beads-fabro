"""Per-wrapper coverage test for bin/next.py."""

from collections.abc import Callable


def test_next_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner("next.py", "livespec_orchestrator_beads_fabro.commands.next", 0)
