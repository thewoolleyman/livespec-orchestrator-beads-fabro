"""Janitor checkout ownership lock."""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "JanitorLock",
    "claim_janitor_lock",
    "janitor_lock_path",
    "release_janitor_lock",
]


@dataclass(frozen=True, kw_only=True)
class JanitorLock:
    work_item_id: str
    pid: int
    started_at_epoch: float


def janitor_lock_path(*, plan: DispatchPlan) -> Path:
    return plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")


def claim_janitor_lock(*, path: Path, owner: str) -> str | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        opened = attempt(
            action=lambda: os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            exceptions=(FileExistsError, OSError),
        )
        if not isinstance(opened, AttemptFailure):
            _write_janitor_lock(descriptor=opened, owner=owner)
            return None
        if not _stale_janitor_lock_reclaimed(path=path):
            return _contention_detail(path=path, owner=owner)
    return _contention_detail(path=path, owner=owner)


def release_janitor_lock(*, path: Path) -> None:
    _ = attempt(action=path.unlink, exceptions=(FileNotFoundError, OSError))


def _write_janitor_lock(*, descriptor: int, owner: str) -> None:
    payload = {
        "pid": os.getpid(),
        "started_at_epoch": time.time(),
        "work_item_id": owner,
    }
    with os.fdopen(descriptor, "wb") as handle:
        _ = handle.write(json.dumps(payload, sort_keys=True).encode())
        _ = handle.write(b"\n")


def _stale_janitor_lock_reclaimed(*, path: Path) -> bool:
    with _reclaim_mutex_path(path=path).open("a+b") as mutex:
        fcntl.flock(mutex.fileno(), fcntl.LOCK_EX)
        return _stale_janitor_lock_reclaimed_locked(path=path)


def _stale_janitor_lock_reclaimed_locked(*, path: Path) -> bool:
    lock = _read_janitor_lock(path=path)
    if lock is None or lock.pid == os.getpid() or _pid_is_alive(pid=lock.pid):
        return False
    if _read_janitor_lock(path=path) != lock:
        return False
    release_janitor_lock(path=path)
    return True


def _reclaim_mutex_path(*, path: Path) -> Path:
    return path.with_name(f"{path.name}.reclaim")


def _read_janitor_lock(*, path: Path) -> JanitorLock | None:
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return None
    parsed_raw = attempt(
        action=lambda: json.loads(read), exceptions=(json.JSONDecodeError, TypeError)
    )
    if isinstance(parsed_raw, AttemptFailure) or not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, object]", parsed_raw)
    return _janitor_lock_from_payload(payload=parsed)


def _janitor_lock_from_payload(*, payload: dict[str, object]) -> JanitorLock | None:
    work_item_raw = payload.get("work_item_id")
    pid_raw = payload.get("pid")
    started_raw = payload.get("started_at_epoch")
    if not isinstance(work_item_raw, str):
        return None
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool) or pid_raw <= 0:
        return None
    if not isinstance(started_raw, int | float) or isinstance(started_raw, bool):
        return None
    return JanitorLock(
        work_item_id=work_item_raw,
        pid=pid_raw,
        started_at_epoch=float(started_raw),
    )


def _contention_detail(*, path: Path, owner: str) -> str:
    lock = _read_janitor_lock(path=path)
    holder = owner if lock is None else lock.work_item_id
    pid_detail = "no pid recorded" if lock is None else f"pid {lock.pid}"
    return (
        f"janitor checkout lock {path} is already held for work-item {holder} "
        f"({pid_detail}). If the pid is present and alive, retry after that process "
        "exits; if the pid is absent or dead and the lock still remains, remove the "
        "stale lock file before retrying."
    )


def _pid_is_alive(*, pid: int) -> bool:
    # Known residual risk: this pidfile lock accepts standard PID-reuse ambiguity.
    probed = attempt(action=lambda: os.kill(pid, 0), exceptions=(OSError,))
    if not isinstance(probed, AttemptFailure):
        return True
    return not isinstance(probed.error, ProcessLookupError)
