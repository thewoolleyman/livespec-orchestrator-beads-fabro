"""Regression coverage for the single analysis shared by coverage gates."""

from __future__ import annotations

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
