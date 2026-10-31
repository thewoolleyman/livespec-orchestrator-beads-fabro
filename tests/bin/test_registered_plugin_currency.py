"""Per-wrapper coverage test for bin/registered_plugin_currency.py."""

from collections.abc import Callable


def test_registered_plugin_currency_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "registered_plugin_currency.py",
        "livespec_orchestrator_beads_fabro.commands.registered_plugin_currency",
        0,
    )
