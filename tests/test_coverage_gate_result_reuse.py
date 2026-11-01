"""Regression coverage for the single analysis shared by coverage gates."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PER_FILE_RECIPE = _ROOT / "dev-tooling" / "just-check-per-file-coverage.sh"
_COVERAGE_RECIPE = _ROOT / "dev-tooling" / "just-check-coverage.sh"


def test_coverage_gates_share_the_canonical_per_file_verdict() -> None:
    """The canonical analyser produces a verdict that the aggregate gate consumes."""
    per_file_recipe = _PER_FILE_RECIPE.read_text(encoding="utf-8")
    coverage_recipe = _COVERAGE_RECIPE.read_text(encoding="utf-8")

    assert "--cov-report=" in per_file_recipe
    assert '--basetemp="${TMPDIR:-/tmp}/pytest"' in per_file_recipe
    assert "python -m livespec_dev_tooling.checks.per_file_coverage" in per_file_recipe
    assert "tee .coverage-gates/per-file.log" in per_file_recipe
    assert ".coverage-gates/per-file.status" in per_file_recipe
    assert "bash dev-tooling/just-check-per-file-coverage.sh" in coverage_recipe
    assert "cat .coverage-gates/per-file.log >&2" in coverage_recipe
    assert ".coverage-gates/per-file.status" in coverage_recipe


def test_coverage_gate_ignores_a_test_failure_after_coverage_passes(
    tmp_path: Path,
) -> None:
    """The aggregate gate replays the verifier result, not pytest's result."""
    repo = tmp_path / "repo"
    tooling = repo / "dev-tooling"
    tooling.mkdir(parents=True)
    for source in (
        _PER_FILE_RECIPE,
        _COVERAGE_RECIPE,
        _ROOT / "dev-tooling" / "just-test-nprocs.sh",
    ):
        _ = shutil.copy2(source, tooling / source.name)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    _ = fake_uv.write_text(
        """#!/usr/bin/env bash
if [[ \"$2\" == pytest ]]; then
    echo 'a test failed' >&2
    exit 1
fi
if [[ \"$2\" == python ]]; then
    echo 'coverage verifier passed'
    exit 0
fi
exit 99
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    env = {
        **os.environ,
        "LIVESPEC_TEST_PARALLELISM": "1",
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }

    producer = subprocess.run(
        ["bash", str(tooling / _PER_FILE_RECIPE.name)],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert producer.returncode == 1
    assert (repo / ".coverage-gates/per-file.status").read_text(encoding="utf-8") == "0\n"

    consumer = subprocess.run(
        ["bash", str(tooling / _COVERAGE_RECIPE.name)],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert consumer.returncode == 0
