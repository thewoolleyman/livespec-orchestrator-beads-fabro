"""Per-wrapper coverage test for bin/factory_bypass_audit.py."""

from collections.abc import Callable


def test_factory_bypass_audit_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "factory_bypass_audit.py",
        "livespec_orchestrator_beads_fabro.commands.factory_bypass_audit",
        0,
    )
