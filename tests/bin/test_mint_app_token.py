"""Per-wrapper coverage test for bin/mint_app_token.py."""

from collections.abc import Callable


def test_mint_app_token_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "mint_app_token.py",
        "livespec_orchestrator_beads_fabro.commands.mint_app_token",
        0,
    )
