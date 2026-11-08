"""The incident authority process preserves command success and refusals."""

from collections.abc import Callable

import pytest


@pytest.mark.parametrize("exit_code", [0, 1, 3])
def test_incident_authority_wrapper_preserves_exit_code(
    *, wrapper_runner: Callable[[str, str, int], None], exit_code: int
) -> None:
    wrapper_runner(
        "incident_authority.py",
        "livespec_orchestrator_beads_fabro.commands.incident_authority",
        exit_code,
    )
