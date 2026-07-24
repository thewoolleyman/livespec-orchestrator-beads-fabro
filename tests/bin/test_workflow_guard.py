"""Per-wrapper coverage test for bin/workflow_guard.py."""

from collections.abc import Callable


def test_workflow_guard_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "workflow_guard.py",
        "livespec_orchestrator_beads_fabro.commands.workflow_guard",
        0,
    )
