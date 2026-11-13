"""Coverage cases for host-wide Fabro deletion pacing."""

from __future__ import annotations

import importlib
import io
import json
import time
from pathlib import Path


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_an_enabled_interval_serializes_active_factory_deletions(tmp_path: Path) -> None:
    factory = f"{tmp_path.name}-{time.time_ns()}"
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {
                            factory: {
                                "defer_collection_while_active": False,
                                "rm_min_interval_seconds": 5,
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    pacing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing"
    )
    journal = _Journal()
    assert pacing.DeletionPacer(repo=tmp_path, now_epoch=lambda: 10.0).permit(
        factory=factory,
        run_id="01A",
        caller="stale-item-reap",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert not pacing.DeletionPacer(repo=tmp_path, now_epoch=lambda: 12.0).permit(
        factory=factory,
        run_id="01B",
        caller="wall-budget-cancel",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert pacing.DeletionPacer(repo=tmp_path, now_epoch=lambda: 15.0).permit(
        factory=factory,
        run_id="01C",
        caller="stall-cancel",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert journal.records[0]["next_deletion_may_start_at"] == 15.0


def test_zero_interval_and_idle_inventory_do_not_defer(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"factories":'
        '{"zero":{"defer_collection_while_active":false,"rm_min_interval_seconds":0}}}}}',
        encoding="utf-8",
    )
    pacing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing"
    )
    journal: list[dict[str, object]] = []
    pacer = pacing.DeletionPacer(repo=tmp_path, now_epoch=lambda: 1.0)
    assert pacer.permit(
        factory="zero",
        run_id="01A",
        caller="reap",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert pacer.permit(
        factory="zero",
        run_id="01B",
        caller="collection",
        has_running_run=False,
        collection=True,
        journal=journal,
    )
    assert journal == []


def test_corrupt_or_non_numeric_state_is_not_a_previous_start() -> None:
    pacing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing"
    )
    assert pacing.previous_start(state=io.StringIO("not-json")) is None
    assert pacing.previous_start(state=io.StringIO("[]")) is None
    assert pacing.previous_start(state=io.StringIO('{"started_at": true}')) is None
