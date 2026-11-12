"""A successful route into needs-human outlives earlier failed stage history."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence


@pytest.mark.parametrize(
    ("stages", "execution", "expected"),
    [
        ({"pr_refresh_head@1": {"state": "failed"}}, (), ("pr_refresh_head@1",)),
        (
            {"pr_refresh_head@1": {"state": "failed"}},
            ("needs_human",),
            ("pr_refresh_head@1",),
        ),
        (
            {"pr_refresh_head@1": {"state": "failed"}},
            ("route", "needs_human"),
            ("pr_refresh_head@1",),
        ),
        (
            {
                "pr_refresh_head@1": {"state": "failed"},
                "route@1": {"state": "failed"},
            },
            ("route", "needs_human"),
            ("route@1", "pr_refresh_head@1"),
        ),
        (
            {
                "pr_refresh_head@1": {"state": "failed"},
                "route@1": {"state": "succeeded"},
            },
            ("route", "needs_human"),
            (),
        ),
    ],
)
def test_only_a_recorded_successful_predecessor_retires_failed_history(
    stages: dict[str, dict[str, object]],
    execution: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    """An incomplete route record must not suppress a real preceding failure."""
    evidence = terminal_evidence(
        payload=[
            {
                "stages": stages,
                "checkpoint": {"current_node": "needs_human"},
                "conclusion": {"stages": list(execution)},
            }
        ]
    )
    assert evidence is not None
    assert evidence.failed_stages == expected
