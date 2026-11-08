"""Per-wrapper coverage test for bin/migrate_claim_tokens.py."""

from collections.abc import Callable


def test_migrate_claim_tokens_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "migrate_claim_tokens.py",
        "livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens",
        1,
    )
