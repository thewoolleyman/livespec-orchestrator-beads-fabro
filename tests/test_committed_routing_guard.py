"""The guard that keeps every test off the committed ACP routing can fire.

`tests/conftest.py` replaces this repository's committed `dispatcher.acp_nodes`
with a tripwire for every test that is not a marked lint. A guard that cannot
return a hit reports a clean suite either way, and its first draft could not:
it watched the overlay resolver, which the preflight path hands a SCOPED copy
of the block. So these are the positive controls: a read of the committed
table trips, a copy of it in another directory trips, a different table reads
normally, and a marked lint reads the real table.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRIPPED = pytest.fail.Exception


def test_reading_the_committed_routing_fails_the_test() -> None:
    table = dispatcher_block(cwd=_REPO_ROOT)["acp_nodes"]

    with pytest.raises(_TRIPPED, match="COMMITTED dispatcher.acp_nodes"):
        _ = table["implement"]


def test_a_copy_of_the_committed_routing_elsewhere_still_trips(tmp_path: Path) -> None:
    shutil.copy(_REPO_ROOT / ".livespec.jsonc", tmp_path / ".livespec.jsonc")
    table = dispatcher_block(cwd=tmp_path)["acp_nodes"]

    with pytest.raises(_TRIPPED, match="COMMITTED dispatcher.acp_nodes"):
        _ = len(table)


def test_a_fixture_routing_reads_normally(tmp_path: Path) -> None:
    fixture = {"implement": {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}}
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": fixture}}}
    (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")

    assert dispatcher_block(cwd=tmp_path)["acp_nodes"] == fixture


@pytest.mark.committed_routing_lint
def test_a_marked_lint_reads_the_real_committed_table() -> None:
    table = dispatcher_block(cwd=_REPO_ROOT)["acp_nodes"]

    assert isinstance(table, dict)
    assert all(isinstance(entry, dict) for entry in table.values())
