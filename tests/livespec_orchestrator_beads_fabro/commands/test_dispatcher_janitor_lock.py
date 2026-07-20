"""Tests for janitor checkout ownership lock helpers."""

import json
import os
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock as janitor_lock
import pytest


def test_claim_janitor_lock_writes_pid_payload_and_release_removes_it(tmp_path: Path) -> None:
    path = tmp_path / "janitor.lock"

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-1")

    assert detail is None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["work_item_id"] == "bd-1"
    assert payload["pid"] == os.getpid()
    assert isinstance(payload["started_at_epoch"], float)

    janitor_lock.release_janitor_lock(path=path)

    assert not path.exists()


def test_claim_janitor_lock_refuses_live_pid_lock(tmp_path: Path) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at_epoch": 1.0,
                "work_item_id": "bd-live",
            }
        ),
        encoding="utf-8",
    )

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "work-item bd-live" in detail
    assert f"pid {os.getpid()}" in detail
    assert "retry after that process exits" in detail


def test_claim_janitor_lock_reclaims_dead_pid_lock(tmp_path: Path) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "started_at_epoch": 1.0,
                "work_item_id": "bd-dead",
            }
        ),
        encoding="utf-8",
    )

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is None
    assert json.loads(path.read_text(encoding="utf-8"))["work_item_id"] == "bd-new"


def test_claim_janitor_lock_refuses_legacy_lock_without_pid(tmp_path: Path) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text("work_item_id=bd-legacy\n", encoding="utf-8")

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "no pid recorded" in detail
    assert "remove the stale lock file" in detail
    assert "Wait for that janitor to finish" not in detail


def test_claim_janitor_lock_treats_unprobeable_pid_as_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text(
        json.dumps(
            {
                "pid": 123,
                "started_at_epoch": 1.0,
                "work_item_id": "bd-hidden",
            }
        ),
        encoding="utf-8",
    )

    def deny_probe(*args: object) -> None:
        _ = args
        raise PermissionError("not visible")

    monkeypatch.setattr(janitor_lock.os, "kill", deny_probe)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "work-item bd-hidden" in detail
    assert "pid 123" in detail


def test_claim_janitor_lock_reports_unknown_owner_for_unreadable_path(tmp_path: Path) -> None:
    detail = janitor_lock.claim_janitor_lock(path=tmp_path, owner="bd-new")

    assert detail is not None
    assert "work-item bd-new" in detail
    assert "no pid recorded" in detail


@pytest.mark.parametrize(
    "payload",
    [
        {"pid": 123, "started_at_epoch": 1.0, "work_item_id": False},
        {"pid": False, "started_at_epoch": 1.0, "work_item_id": "bd-bad"},
        {"pid": 123, "started_at_epoch": False, "work_item_id": "bd-bad"},
    ],
)
def test_claim_janitor_lock_refuses_invalid_json_payloads(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text(json.dumps(payload), encoding="utf-8")

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "no pid recorded" in detail


def test_claim_janitor_lock_preserves_live_replacement_when_stale_reclaim_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "janitor.lock"
    stale_payload = {
        "pid": 999_999_999,
        "started_at_epoch": 1.0,
        "work_item_id": "bd-stale",
    }
    live_payload = {
        "pid": os.getpid(),
        "started_at_epoch": 2.0,
        "work_item_id": "bd-live-replacement",
    }
    path.write_text(json.dumps(stale_payload), encoding="utf-8")
    live_bytes = json.dumps(live_payload, sort_keys=True).encode() + b"\n"

    def replace_stale_with_live(*, pid: int) -> bool:
        # The probe is now consulted for the live replacement pid as well, since
        # the production-dead `lock.pid == os.getpid()` short-circuit is gone.
        # Only the stale pid triggers the swap; the live pid reports alive.
        if pid != stale_payload["pid"]:
            return True
        path.write_bytes(live_bytes)
        return False

    monkeypatch.setattr(janitor_lock, "_pid_is_alive", replace_stale_with_live)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-racing-claimant")

    assert detail is not None
    assert "work-item bd-live-replacement" in detail
    assert path.read_bytes() == live_bytes

    third_detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-third")

    assert third_detail is not None
    assert path.read_bytes() == live_bytes


def test_claim_janitor_lock_reports_contention_when_reclaim_race_loses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "janitor.lock"
    path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "started_at_epoch": 1.0,
                "work_item_id": "bd-dead",
            }
        ),
        encoding="utf-8",
    )

    def refuse_open(*args: object) -> int:
        _ = args
        raise FileExistsError("still held")

    def keep_stale_lock(*, path: Path) -> None:
        _ = path

    monkeypatch.setattr(janitor_lock.os, "open", refuse_open)
    monkeypatch.setattr(janitor_lock, "release_janitor_lock", keep_stale_lock)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    assert detail is not None
    assert "work-item bd-dead" in detail
