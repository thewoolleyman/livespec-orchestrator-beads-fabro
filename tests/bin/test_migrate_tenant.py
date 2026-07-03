"""Per-wrapper coverage test for bin/migrate_tenant.py."""

from collections.abc import Callable


def test_migrate_tenant_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "migrate_tenant.py",
        "livespec_orchestrator_beads_fabro.commands.migrate_tenant",
        0,
    )
