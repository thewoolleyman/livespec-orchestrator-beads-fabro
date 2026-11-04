"""Scenario 304 — the check aggregate refuses real-time sleeps and wall-clock verdicts.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 304 — The check aggregate refuses a test that sleeps in real time or
judges a wall-clock bound, unless an exemption marker states why`. The clause it
realizes is the real-time-test bullet of the forbidden-patterns list in
`SPECIFICATION/constraints.md`, cited at the FILE level so a heading rename cannot
rot it.

The case drives the gate's own composition (`findings`) over a seeded tests tree
that carries the scenario's two offending files, with the COMMITTED control
fixture copied in so both positive controls run for real, and then walks the
scenario's exemption steps on the sleeping file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "tests_no_real_time.py"
_CONTROL_FIXTURE = Path("dev-tooling") / "checks" / "fixtures" / "real_time_control.py.txt"

_SLEEPING = "import time\n\n\ndef test_waits() -> None:\n    time.sleep(0.25)\n"
_SLEEPING_REASONED = (
    "import time\n"
    "\n"
    "\n"
    "def test_waits() -> None:\n"
    "    time.sleep(0.25)  # real-time-required: the host clock is this test's subject\n"
)
_SLEEPING_UNREASONED = (
    "import time\n\n\ndef test_waits() -> None:\n    time.sleep(0.25)  # real-time-required:\n"
)
_JUDGING = (
    "import time\n"
    "\n"
    "\n"
    "def test_bounds() -> None:\n"
    "    start = time.monotonic()\n"
    "    elapsed = time.monotonic() - start\n"
    "    assert elapsed < 1\n"
)


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tests_no_real_time", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed(*, root: Path, sleeping: str) -> None:
    fixture = root / _CONTROL_FIXTURE
    fixture.parent.mkdir(parents=True, exist_ok=True)
    _ = fixture.write_text(
        (_REPO_ROOT / _CONTROL_FIXTURE).read_text(encoding="utf-8"), encoding="utf-8"
    )
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    _ = (tests / "test_sleeps.py").write_text(sleeping, encoding="utf-8")
    _ = (tests / "test_judges.py").write_text(_JUDGING, encoding="utf-8")


def test_scenario304_a_sleep_and_a_wall_clock_verdict_are_refused_and_a_reasoned_marker_is_honoured(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = _load_check()
    monkeypatch.setattr(check, "MINIMUM_SCANNED_FILES", 1)

    _seed(root=tmp_path, sleeping=_SLEEPING)
    refused = check.findings(repo_root=tmp_path)
    assert refused == [
        "tests/test_judges.py:7: asserts on a difference of real clock readings",
        "tests/test_sleeps.py:5: waits in real time through time.sleep",
    ]

    _seed(root=tmp_path, sleeping=_SLEEPING_REASONED)
    assert check.findings(repo_root=tmp_path) == [
        "tests/test_judges.py:7: asserts on a difference of real clock readings"
    ]

    _seed(root=tmp_path, sleeping=_SLEEPING_UNREASONED)
    assert "tests/test_sleeps.py:5: carries an exemption marker with no written reason" in (
        check.findings(repo_root=tmp_path)
    )

    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    assert (
        "check-tests-no-real-time" in justfile.split("targets=(", 1)[1].split("\n)", 1)[0].split()
    )
