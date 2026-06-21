"""Per-wrapper coverage test for bin/detect_impl_gaps.py."""

from collections.abc import Callable


def test_detect_impl_gaps_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "detect_impl_gaps.py",
        "livespec_orchestrator_beads_fabro.commands.detect_impl_gaps",
        0,
    )
