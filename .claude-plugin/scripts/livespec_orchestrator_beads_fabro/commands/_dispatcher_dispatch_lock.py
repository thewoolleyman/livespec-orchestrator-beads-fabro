"""Dispatch-scoped ownership lock for reconcile-merged."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = [
    "DispatchLock",
    "dispatch_lock_path",
    "live_dispatch_lock",
    "release_dispatch_lock",
    "write_dispatch_lock",
]


@dataclass(frozen=True, kw_only=True)
class DispatchLock:
    work_item_id: str
    pid: int
    started_at_epoch: float
    dispatch_id: str | None


def dispatch_lock_path(*, repo: Path, work_item_id: str) -> Path:
    return repo / "tmp" / f"fabro-dispatch-{work_item_id}.lock"


def write_dispatch_lock(*, repo: Path, work_item_id: str, dispatch_id: str) -> Path:
    path = dispatch_lock_path(repo=repo, work_item_id=work_item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "work_item_id": work_item_id,
        "pid": os.getpid(),
        "started_at_epoch": time.time(),
        "dispatch_id": dispatch_id,
    }
    _ = path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def release_dispatch_lock(*, path: Path) -> None:
    _ = attempt(action=path.unlink, exceptions=(FileNotFoundError, OSError))


def live_dispatch_lock(*, repo: Path, work_item_id: str) -> DispatchLock | None:
    path = dispatch_lock_path(repo=repo, work_item_id=work_item_id)
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return None
    parsed_raw = parse_json(text=read)
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, object]", parsed_raw)
    lock = _dispatch_lock_from_payload(payload=parsed, expected_work_item_id=work_item_id)
    if lock is None or not _pid_is_alive(pid=lock.pid):
        return None
    return lock


def _dispatch_lock_from_payload(
    *, payload: dict[str, object], expected_work_item_id: str
) -> DispatchLock | None:
    work_item_raw = payload.get("work_item_id")
    pid_raw = payload.get("pid")
    started_raw = payload.get("started_at_epoch")
    dispatch_id_raw = payload.get("dispatch_id")
    if work_item_raw != expected_work_item_id:
        return None
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool) or pid_raw <= 0:
        return None
    if not isinstance(started_raw, int | float) or isinstance(started_raw, bool):
        return None
    if dispatch_id_raw is not None and not isinstance(dispatch_id_raw, str):
        return None
    return DispatchLock(
        work_item_id=expected_work_item_id,
        pid=pid_raw,
        started_at_epoch=float(started_raw),
        dispatch_id=dispatch_id_raw,
    )


def _pid_is_alive(*, pid: int) -> bool:
    probed = attempt(action=lambda: os.kill(pid, 0), exceptions=(OSError,))
    if not isinstance(probed, AttemptFailure):
        return True
    return not isinstance(probed.error, ProcessLookupError)
