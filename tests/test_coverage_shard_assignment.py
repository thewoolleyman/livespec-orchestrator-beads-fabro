"""Behavioral coverage for the duration-balanced coverage shard assignment.

`dev-tooling/just-coverage-shard.sh <i> <N>` places the longest remaining test
file on the shard with the smallest running total, using a committed
per-test-file duration table. `LIVESPEC_COVERAGE_SHARD_LIST_ONLY=1` makes it
print the shard's test files and stop, so the plan is observable without
running pytest. The table location is overridable through
`LIVESPEC_COVERAGE_SHARD_DURATIONS` so a test can supply its own.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "dev-tooling" / "just-coverage-shard.sh"


def _make_repo(*, root: Path, tracked: list[str]) -> None:
    """Create a git repo whose index tracks the named (empty) files."""
    _ = subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    for name in tracked:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text("", encoding="utf-8")
    _ = subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)


def _shard_files(*, root: Path, table: Path, index: int, count: int) -> list[str]:
    """Return the files the script assigns to shard `index` of `count`."""
    completed = subprocess.run(
        ["bash", str(_SCRIPT), str(index), str(count)],
        capture_output=True,
        check=False,
        cwd=root,
        env={
            **os.environ,
            "LIVESPEC_COVERAGE_SHARD_LIST_ONLY": "1",
            "LIVESPEC_COVERAGE_SHARD_DURATIONS": str(table),
        },
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.split()


def _write_table(*, path: Path, durations: dict[str, float]) -> None:
    rows = "".join(f"{name}\t{seconds}\n" for name, seconds in durations.items())
    _ = path.write_text(rows, encoding="utf-8")


def test_longest_remaining_file_goes_to_the_smallest_running_total(tmp_path: Path) -> None:
    durations = {
        "tests/test_a.py": 10.0,
        "tests/test_b.py": 9.0,
        "tests/test_c.py": 8.0,
        "tests/test_d.py": 7.0,
        "tests/test_e.py": 6.0,
        "tests/test_f.py": 5.0,
    }
    repo = tmp_path / "repo"
    _make_repo(root=repo, tracked=list(durations))
    table = tmp_path / "durations.tsv"
    _write_table(path=table, durations=durations)

    first = _shard_files(root=repo, table=table, index=1, count=2)
    second = _shard_files(root=repo, table=table, index=2, count=2)

    assert sorted(first) == ["tests/test_a.py", "tests/test_d.py", "tests/test_e.py"]
    assert sorted(second) == ["tests/test_b.py", "tests/test_c.py", "tests/test_f.py"]


def test_every_tracked_file_lands_in_exactly_one_shard_even_when_absent_from_the_table(
    tmp_path: Path,
) -> None:
    listed = {
        f"tests/test_{name}.py": float(seconds)
        for name, seconds in zip("abcdef", range(10, 4, -1), strict=True)
    }
    tracked = [*listed, "tests/sub/test_unlisted.py", "tests/unlisted_test.py", "tests/helper.py"]
    repo = tmp_path / "repo"
    _make_repo(root=repo, tracked=tracked)
    table = tmp_path / "durations.tsv"
    _write_table(path=table, durations={**listed, "tests/test_deleted.py": 99.0})

    assigned = [
        name
        for index in range(1, 5)
        for name in _shard_files(root=repo, table=table, index=index, count=4)
    ]

    expected = sorted([*listed, "tests/sub/test_unlisted.py", "tests/unlisted_test.py"])
    assert sorted(assigned) == expected
