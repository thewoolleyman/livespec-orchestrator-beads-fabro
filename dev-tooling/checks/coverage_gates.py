"""Analyse coverage data once, then let both coverage gates read its result."""

# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import TypedDict, cast

import livespec_dev_tooling

_VENDOR_DIR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.append(str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path append.
from coverage import Coverage  # noqa: E402  — available after the vendor path is configured.

__all__: list[str] = ["analyse", "check_coverage", "check_per_file", "main"]

_DATA_FILE = ".coverage"
_RESULT_FILE = ".coverage-gates.json"
_FULL_COVERAGE = 100.0


class _CoverageSummary(TypedDict):
    percent_covered: float


class _CoverageFile(TypedDict):
    summary: _CoverageSummary


class _CoverageReport(TypedDict):
    files: dict[str, _CoverageFile]


class _GateResult(TypedDict):
    offenders: list[str]


def _result_path(*, cwd: Path) -> Path:
    return cwd / _RESULT_FILE


def analyse() -> int:
    """Write the one report-analysis result consumed by both coverage gates."""
    cwd = Path.cwd()
    cov = Coverage(data_file=str(cwd / _DATA_FILE))
    cov.load()
    report_output = io.StringIO()
    with redirect_stdout(report_output):
        _ = cov.json_report(outfile="-")
    report = cast(_CoverageReport, json.loads(report_output.getvalue()))
    result: _GateResult = {
        "offenders": sorted(
            filename
            for filename, detail in report["files"].items()
            if detail["summary"]["percent_covered"] < _FULL_COVERAGE
        )
    }
    _ = _result_path(cwd=cwd).write_text(json.dumps(result), encoding="utf-8")
    return 0


def _offenders(*, cwd: Path) -> list[str]:
    result = cast(_GateResult, json.loads(_result_path(cwd=cwd).read_text(encoding="utf-8")))
    return result["offenders"]


def _check() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("coverage_gates")
    offenders = _offenders(cwd=Path.cwd())
    for filename in offenders:
        log.error("file below 100% coverage", file=filename)
    return int(bool(offenders))


def check_per_file() -> int:
    """Apply the per-file gate to the shared coverage-analysis result."""
    return _check()


def check_coverage() -> int:
    """Apply the aggregate gate to the shared coverage-analysis result."""
    return _check()


def main() -> int:
    commands: dict[str, Callable[[], int]] = {
        "analyse": analyse,
        "per-file": check_per_file,
        "coverage": check_coverage,
    }
    return commands[sys.argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main())
