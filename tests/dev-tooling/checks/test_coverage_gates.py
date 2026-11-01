"""Tests for the single-pass coverage-result gate helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "coverage_gates.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coverage_gates", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeCoverage:
    def __init__(self, *, data_file: str, report: dict[str, object]) -> None:
        self.data_file = data_file
        self.report = report

    def load(self) -> None:
        return None

    def json_report(self, *, outfile: str) -> float:
        assert outfile == "-"
        _ = sys.stdout.write(json.dumps(self.report))
        return 0.0


def _coverage_report(*, percentage: float) -> dict[str, object]:
    return {
        "files": {
            "covered.py": {"summary": {"percent_covered": 100.0}},
            "missed.py": {"summary": {"percent_covered": percentage}},
        }
    }


def _coverage_factory(*, report: dict[str, object]) -> Callable[..., _FakeCoverage]:
    def factory(*, data_file: str) -> _FakeCoverage:
        return _FakeCoverage(data_file=data_file, report=report)

    return factory


def test_one_analysis_result_drives_both_failing_gates(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _CHECK_PATH.is_file()
    check = _load_check()
    coverage_file = tmp_path / ".coverage"
    coverage_file.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        check,
        "Coverage",
        _coverage_factory(report=_coverage_report(percentage=75.0)),
    )

    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "analyse"])
    assert check.main() == 0
    result = json.loads((tmp_path / ".coverage-gates.json").read_text(encoding="utf-8"))
    assert result == {"offenders": ["missed.py"]}

    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "per-file"])
    assert check.main() == 1
    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "coverage"])
    assert check.main() == 1
    assert capsys.readouterr().err.count("missed.py") == 2


def test_one_analysis_result_allows_both_passing_gates(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    check = _load_check()
    coverage_file = tmp_path / ".coverage"
    coverage_file.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        check,
        "Coverage",
        _coverage_factory(report=_coverage_report(percentage=100.0)),
    )

    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "analyse"])
    assert check.main() == 0
    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "per-file"])
    assert check.main() == 0
    monkeypatch.setattr(sys, "argv", [str(_CHECK_PATH), "coverage"])
    assert check.main() == 0
