"""Per-wrapper coverage test for bin/factory_provenance_check.py."""

from collections.abc import Callable


def test_factory_provenance_check_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "factory_provenance_check.py",
        "livespec_orchestrator_beads_fabro.commands.factory_provenance_check",
        1,
    )
