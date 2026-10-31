"""Failure controls for Scenario 184's conflict-set measurement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    measure_conflicted_paths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return self.result


@pytest.mark.parametrize(
    "result, expected_failure",
    [
        (CommandResult(exit_code=128, stdout="", stderr="bad revision"), "bad revision"),
        (CommandResult(exit_code=1, stdout="", stderr=""), "named no conflicted paths"),
    ],
)
def test_an_uncomputable_conflict_set_names_the_failed_measurement(
    tmp_path: Path, result: CommandResult, expected_failure: str
) -> None:
    """Neither a Git failure nor an empty answer can admit automatic recovery."""
    measured = measure_conflicted_paths(
        repo=tmp_path,
        runner=_Runner(result=result),
        pr_head="head1111",
        default_branch_tip="base2222",
    )

    assert measured.paths is None
    assert measured.failure is not None
    assert expected_failure in measured.failure
