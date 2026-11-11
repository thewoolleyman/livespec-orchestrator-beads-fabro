"""Behavioral coverage for the coverage shard duration table regeneration.

The `coverage-shard-durations` just recipe runs pytest once with per-test
timings and writes the committed table `dev-tooling/coverage-shard-durations.tsv`,
one `<test file path><TAB><seconds>` row per test file. `LIVESPEC_COVERAGE_SHARD_PYTEST_LOG`
supplies a saved pytest run instead of running one, and
`LIVESPEC_COVERAGE_SHARD_DURATIONS_OUT` names the table to write.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "dev-tooling" / "just-coverage-shard-durations.sh"
_JUSTFILE = _ROOT / "justfile"

_PYTEST_LOG = """\
============================= slowest durations ==============================
12.50s call     tests/test_a.py::test_one
0.30s setup    tests/test_a.py::test_one
0.20s teardown tests/test_a.py::test_one
1.00s call     tests/sub/test_b.py::TestX::test_y[param-1]
2.25s call     tests/sub/test_b.py::TestX::test_y[param-2]
0.05s call     tests/other_test.py::test_z
(3 durations < 0.005s hidden.  Use -vv to show these durations.)
=========================== 6 passed in 20.00s ===========================
"""


def _regenerate(*, tmp_path: Path, log_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    log = tmp_path / "pytest.log"
    _ = log.write_text(log_text, encoding="utf-8")
    out = tmp_path / "durations.tsv"
    completed = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "LIVESPEC_COVERAGE_SHARD_PYTEST_LOG": str(log),
            "LIVESPEC_COVERAGE_SHARD_DURATIONS_OUT": str(out),
        },
        text=True,
    )
    return completed, out


def test_regeneration_sums_per_test_timings_by_test_file_path(tmp_path: Path) -> None:
    completed, out = _regenerate(tmp_path=tmp_path, log_text=_PYTEST_LOG)

    assert completed.returncode == 0, completed.stderr
    assert out.read_text(encoding="utf-8").splitlines() == [
        "tests/other_test.py\t0.050",
        "tests/sub/test_b.py\t3.250",
        "tests/test_a.py\t13.000",
    ]


def test_regeneration_refuses_a_run_with_no_timings_and_keeps_the_existing_table(
    tmp_path: Path,
) -> None:
    out = tmp_path / "durations.tsv"
    _ = out.write_text("tests/test_keep.py\t1.000\n", encoding="utf-8")

    completed, _ = _regenerate(tmp_path=tmp_path, log_text="no timings here\n")

    assert completed.returncode != 0
    assert out.read_text(encoding="utf-8") == "tests/test_keep.py\t1.000\n"


def test_a_just_recipe_regenerates_the_table() -> None:
    recipe = re.search(
        r"^coverage-shard-durations:\n\s+(\S+)\n",
        _JUSTFILE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )

    assert recipe is not None
    assert recipe.group(1) == "dev-tooling/just-coverage-shard-durations.sh"
