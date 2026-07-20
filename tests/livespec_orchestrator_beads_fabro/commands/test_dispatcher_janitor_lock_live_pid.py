"""Live-PID janitor lock coverage tests."""

import json
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock as janitor_lock


def test_claim_janitor_lock_refuses_pid_one_lock_without_rewriting_bytes(tmp_path: Path) -> None:
    path = tmp_path / "janitor.lock"
    original = (
        json.dumps(
            {
                "pid": 1,
                "started_at_epoch": 1.0,
                "work_item_id": "bd-live",
            },
            sort_keys=True,
        )
        + "\n"
    )
    path.write_text(original, encoding="utf-8")

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "work-item bd-live" in detail
    assert "pid 1" in detail
    assert path.read_text(encoding="utf-8") == original
