"""Coverage for the timeout boundary in the preserve-pointer regression double."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _preserve_reference_tests() -> ModuleType:
    path = Path(__file__).with_name("test_dispatcher_preserve_reference.py")
    spec = importlib.util.spec_from_file_location("preserve_reference_regression", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_slow_dump_double_times_out_below_its_six_hundred_second_completion(
    tmp_path: Path,
) -> None:
    runner_type = _preserve_reference_tests().__dict__["_SixHundredSecondDumpRunner"]
    runner = runner_type()

    result = runner.run(
        argv=["fabro", "dump", "01M0RUN", "-o", str(tmp_path / "export")],
        cwd=tmp_path,
        timeout_seconds=300,
    )

    assert result.exit_code == 124
    assert runner.timeouts == [300]
