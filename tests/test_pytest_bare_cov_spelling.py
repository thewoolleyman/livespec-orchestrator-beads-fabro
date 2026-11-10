"""A bare ``pytest --cov=<pkg>`` run must not fail combining coverage data.

``[tool.coverage.run] branch = true`` lives in ``pyproject.toml``. pytest-cov hands
its test subprocesses the coverage config by path only when ``--cov-config`` names
an existing file; with the bare spelling the default ``.coveragerc`` is assumed and
does not exist. A subprocess whose cwd has no ``pyproject.toml`` in view then
measures statements only, and the parent's combine step raises INTERNALERROR
("Can't combine statement coverage data with branch data") after the suite passed.

The test builds a throwaway project from this repository's REAL pytest section and
runs the bare spelling there, with a test that starts one subprocess inside the
project (where coverage finds ``pyproject.toml`` by itself) and one outside it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import tomli

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMBINE_ERROR = "Can't combine statement coverage data with branch data"
_INNER_TEST = """\
import subprocess
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[1]


def test_subprocesses_in_and_outside_the_project() -> None:
    elsewhere = _PROJECT / "elsewhere"
    elsewhere.mkdir()
    for cwd in (_PROJECT, elsewhere):
        done = subprocess.run(
            [sys.executable, "-c", "import widget; widget.double(2)"],
            cwd=cwd,
            check=False,
        )
        assert done.returncode == 0
"""


def _build_project(*, root: Path) -> None:
    pytest_section = tomli.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["pytest"]["ini_options"]
    addopts = json.dumps(pytest_section["addopts"])
    (root / "pyproject.toml").write_text(
        f"[tool.pytest.ini_options]\naddopts = {addopts}\n\n[tool.coverage.run]\nbranch = true\n",
        encoding="utf-8",
    )
    (root / "widget.py").write_text(
        "def double(x: int) -> int:\n    if x:\n        return x * 2\n    return 0\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_inner.py").write_text(_INNER_TEST, encoding="utf-8")


def _run_bare(*, root: Path, extra: list[str]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_", "PYTEST_"))
    }
    env["PYTHONPATH"] = str(root)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *extra],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bare_cov_run_ends_with_pytests_own_status_and_a_report(tmp_path: Path) -> None:
    _build_project(root=tmp_path)
    done = _run_bare(root=tmp_path, extra=["--cov=widget"])
    output = done.stdout + done.stderr
    assert _COMBINE_ERROR not in output, output
    assert done.returncode == 0, output
    assert "coverage:" in output, output


def test_run_without_cov_still_collects_and_runs_the_tests(tmp_path: Path) -> None:
    _build_project(root=tmp_path)
    done = _run_bare(root=tmp_path, extra=[])
    output = done.stdout + done.stderr
    assert done.returncode == 0, output
    assert "1 passed" in output, output
