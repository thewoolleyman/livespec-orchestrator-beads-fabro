"""The host `check` command names every outstanding wait mismatch distinctly.

Scenario 158 requires the turn-end check to expose an ended unacknowledged
target, and the Definition of Done requires it to tell overdue waits, missing
waiter processes and unavailable inventory apart from a healthy wait. The
inventory payload already carries per-record findings; the `check` summary is
what a session reads before it parks, so it has to list each mismatch with its
source, its wait and its record state rather than leave the reader to scan rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)

_LIVE_PID = 4242
_LIVE_GENERATION = "generation-live"


def _write_wait(
    *,
    wait_root: Path,
    wait_id: str,
    waiter_pid: int = _LIVE_PID,
    deadline_at: float = 1000.0,
    acknowledged: bool = False,
) -> None:
    wait_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "acknowledgement": {
            "acknowledged": acknowledged,
            "acknowledged_at": 20.0 if acknowledged else None,
            "kind": "receipt-only" if acknowledged else None,
            "session_id": None,
        },
        "armed_at": 10.0,
        "deadline_at": deadline_at,
        "deadline_seconds": deadline_at - 10.0,
        "observation_sequence": 0,
        "observations": [],
        "repository": str(wait_root.parent.parent),
        "return_ready": False,
        "return_reason": None,
        "schema_version": 1,
        "session_id": "session-check",
        "targets": [
            {
                "kind": "gate",
                "gate_store_root": str(wait_root.parent / "gate-runs"),
                "run_id": f"run-{wait_id}",
                "generation": "generation-run",
            }
        ],
        "wait_id": wait_id,
        "waiter": {"generation": _LIVE_GENERATION, "pid": waiter_pid},
    }
    _ = (wait_root / f"{wait_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _seams(*, target_state: str, now: float) -> session_wait.SessionWaitCliSeams:
    def observe(*, target: WaitTarget, observed_at: float) -> GateObservation:
        if target_state == "RUNNING":
            return GateObservation.running(target=target, observed_at=observed_at)
        return GateObservation.finished(
            target=target, state=target_state, exit_code=23, observed_at=observed_at
        )

    def generation(*, pid: int) -> str | None:
        return None if pid == 0 else _LIVE_GENERATION

    return session_wait.SessionWaitCliSeams(
        primary_repository=lambda *, repository: repository,
        launcher=lambda *, repository: repository,  # type: ignore[arg-type,return-value]
        observe_target=observe,
        process_generation=generation,
        wall_clock=lambda: now,
        use_tmp_directory=True,
    )


def _check(
    *, primary: Path, seams: session_wait.SessionWaitCliSeams, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, object]]:
    code = session_wait.main(argv=["check", "--repo", str(primary)], seams=seams)
    return code, json.loads(capsys.readouterr().out)


def _summary(*, payload: dict[str, object]) -> dict[str, object]:
    assert "summary" in payload
    summary = payload["summary"]
    assert isinstance(summary, dict)
    return summary


def test_check_summary_lists_an_ended_unacknowledged_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_wait(wait_root=tmp_path / "tmp" / "session-waits", wait_id="wait-ended")

    code, payload = _check(
        primary=tmp_path, seams=_seams(target_state="FAILED", now=500.0), capsys=capsys
    )

    assert code == 1
    assert _summary(payload=payload) == {
        "findings": [
            {
                "finding": "ended-unacknowledged",
                "id": "wait-ended",
                "record_state": "available",
                "source": "wait",
            }
        ],
        "healthy": False,
    }


def test_check_summary_distinguishes_overdue_missing_waiter_and_unavailable_from_healthy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wait_root = tmp_path / "tmp" / "session-waits"
    _write_wait(wait_root=wait_root, wait_id="wait-healthy")
    _write_wait(wait_root=wait_root, wait_id="wait-overdue", deadline_at=100.0)
    _write_wait(wait_root=wait_root, wait_id="wait-orphaned", waiter_pid=0)
    _ = (wait_root / "wait-corrupt.json").write_text("{not json", encoding="utf-8")

    code, payload = _check(
        primary=tmp_path, seams=_seams(target_state="RUNNING", now=500.0), capsys=capsys
    )

    findings = _summary(payload=payload)["findings"]
    assert isinstance(findings, list)
    assert code == 1
    assert {(entry["id"], entry["finding"], entry["record_state"]) for entry in findings} == {
        ("wait-overdue", "overdue", "available"),
        ("wait-orphaned", "waiter-missing", "available"),
        ("wait-orphaned", "running-without-waiter", "available"),
        ("wait-corrupt", "invalid-record", "unavailable"),
    }
    assert all(entry["source"] == "wait" for entry in findings)


def test_check_summary_of_an_acknowledged_completed_wait_is_healthy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_wait(
        wait_root=tmp_path / "tmp" / "session-waits",
        wait_id="wait-acked",
        waiter_pid=0,
        acknowledged=True,
    )

    code, payload = _check(
        primary=tmp_path, seams=_seams(target_state="FAILED", now=500.0), capsys=capsys
    )

    assert code == 0
    assert _summary(payload=payload) == {"findings": [], "healthy": True}


def test_check_summary_of_an_empty_store_is_healthy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _check(
        primary=tmp_path, seams=_seams(target_state="RUNNING", now=500.0), capsys=capsys
    )

    assert code == 0
    assert _summary(payload=payload) == {"findings": [], "healthy": True}
