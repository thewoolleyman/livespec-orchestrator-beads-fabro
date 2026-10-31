"""The read-only conflict measurement behind Scenario 184's record-file arm."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files"


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    argv: list[str] | None = None

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.argv = argv
        return self.result


def test_the_measurement_returns_every_path_from_the_read_only_merge_command(
    tmp_path: Path,
) -> None:
    """Its output is the exact path set later compared with record_files."""
    module = importlib.import_module(_MODULE)
    measure = getattr(module, "measure_conflicted_paths", None)
    assert callable(measure), "the overtaken-arming conflict measurement is not implemented"
    runner = _Runner(
        result=CommandResult(
            exit_code=1,
            stdout="SPECIFICATION/scenarios.md\ntests/heading-coverage.json\n",
            stderr="",
        )
    )

    measured = measure(
        repo=tmp_path,
        runner=runner,
        pr_head="head1111",
        default_branch_tip="base2222",
    )

    assert measured.paths == ("SPECIFICATION/scenarios.md", "tests/heading-coverage.json")
    assert measured.failure is None
    assert runner.argv == [
        "git",
        "merge-tree",
        "--write-tree",
        "--name-only",
        "head1111",
        "base2222",
    ]
