"""Per-wrapper coverage test for bin/drive.py."""

from collections.abc import Callable


def test_drive_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "drive.py",
        "livespec_orchestrator_beads_fabro.commands.drive",
        0,
    )
