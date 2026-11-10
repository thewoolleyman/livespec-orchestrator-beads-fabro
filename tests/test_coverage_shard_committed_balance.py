"""The committed duration table balances the four CI coverage shards.

`.github/workflows/ci.yml` runs `just coverage-shard <i> 4` for i in 1..4; the
job that finishes last sets the critical path. Given the committed table
`dev-tooling/coverage-shard-durations.tsv`, the summed recorded durations of
the four shards must differ by at most 10 percent of the largest shard's sum.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "dev-tooling" / "just-coverage-shard.sh"
_TABLE = _ROOT / "dev-tooling" / "coverage-shard-durations.tsv"
_SHARD_COUNT = 4


def _table() -> dict[str, float]:
    rows = [line.split("\t") for line in _TABLE.read_text(encoding="utf-8").splitlines()]
    return {name: float(seconds) for name, seconds in rows}


def _shard_files(*, index: int) -> list[str]:
    completed = subprocess.run(
        ["bash", str(_SCRIPT), str(index), str(_SHARD_COUNT)],
        capture_output=True,
        check=False,
        cwd=_ROOT,
        env={**os.environ, "LIVESPEC_COVERAGE_SHARD_LIST_ONLY": "1"},
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.split()


def test_committed_table_balances_the_shards_within_ten_percent() -> None:
    table = _table()
    sums = [
        sum(table.get(name, 0.0) for name in _shard_files(index=index))
        for index in range(1, _SHARD_COUNT + 1)
    ]

    assert min(sums) > 0.0
    assert max(sums) - min(sums) <= 0.10 * max(sums), sums
