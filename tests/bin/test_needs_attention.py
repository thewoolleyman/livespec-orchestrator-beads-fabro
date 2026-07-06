"""Per-wrapper coverage test for bin/needs_attention.py."""

from collections.abc import Callable


def test_needs_attention_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "needs_attention.py",
        "livespec_orchestrator_beads_fabro.commands.needs_attention",
        0,
    )
