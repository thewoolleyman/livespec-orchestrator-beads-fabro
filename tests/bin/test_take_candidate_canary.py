"""Per-wrapper coverage test for bin/take_candidate_canary.py."""

from collections.abc import Callable


def test_take_candidate_canary_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "take_candidate_canary.py",
        "livespec_orchestrator_beads_fabro.commands.take_candidate_canary",
        0,
    )
