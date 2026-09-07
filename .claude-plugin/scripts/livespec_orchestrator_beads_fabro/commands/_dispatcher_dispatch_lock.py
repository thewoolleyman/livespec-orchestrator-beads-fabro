"""Dispatch-scoped ownership lock for reconcile-merged."""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_pid_liveness import (
    process_started_at_epoch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tenant_checkouts import (
    register_tenant_checkout,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = [
    "DispatchLock",
    "dispatch_lock_path",
    "live_dispatch_lock",
    "recorded_dispatch_lock",
    "release_dispatch_lock",
    "write_dispatch_lock",
]

_PROCESS_START_TOLERANCE_SECONDS = 2.0


@dataclass(frozen=True, kw_only=True)
class DispatchLock:
    work_item_id: str
    pid: int
    started_at_epoch: float
    dispatch_id: str | None


def dispatch_lock_path(*, repo: Path, work_item_id: str) -> Path:
    return repo / "tmp" / f"fabro-dispatch-{work_item_id}.lock"


def write_dispatch_lock(*, repo: Path, work_item_id: str, dispatch_id: str) -> Path:
    # Register BEFORE the claim is attempted, not after it succeeds: the WIP-cap
    # bound is TENANT-scoped, and a checkout whose lock this call is about to
    # write must already be enumerable by every sibling checkout counting claims.
    register_tenant_checkout(repo=repo)
    path = dispatch_lock_path(repo=repo, work_item_id=work_item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    opened = _open_dispatch_lock(path=path)
    if not isinstance(opened, AttemptFailure):
        _write_dispatch_lock(descriptor=opened, work_item_id=work_item_id, dispatch_id=dispatch_id)
        return path
    if not isinstance(opened.error, FileExistsError):
        raise opened.error
    if not _stale_dispatch_lock_reclaimed(path=path, work_item_id=work_item_id):
        raise opened.error
    retry = _open_dispatch_lock(path=path)
    if not isinstance(retry, AttemptFailure):
        _write_dispatch_lock(descriptor=retry, work_item_id=work_item_id, dispatch_id=dispatch_id)
        return path
    raise retry.error


def _open_dispatch_lock(*, path: Path) -> int | AttemptFailure:
    return attempt(
        action=lambda: os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        exceptions=(FileExistsError, OSError),
    )


def _write_dispatch_lock(*, descriptor: int, work_item_id: str, dispatch_id: str) -> None:
    payload = {
        "work_item_id": work_item_id,
        "pid": os.getpid(),
        "started_at_epoch": time.time(),
        "dispatch_id": dispatch_id,
    }
    with os.fdopen(descriptor, "wb") as handle:
        _ = handle.write(json.dumps(payload, sort_keys=True).encode())
        _ = handle.write(b"\n")


def release_dispatch_lock(*, path: Path) -> None:
    _ = attempt(action=path.unlink, exceptions=(FileNotFoundError, OSError))


def recorded_dispatch_lock(*, repo: Path, work_item_id: str) -> DispatchLock | None:
    """The claim written for this row, whether or not its writer is still running.

    `live_dispatch_lock` answers "is a dispatch in flight?"; this answers the
    prior question "was a claim written, and by whom?". They differ for exactly
    one caller that matters: the groom door writes its claim and then EXITS, so
    a reader that gates on the writer being alive cannot recognise the door's
    own claim at all — which is what made a door-claimed item unlaunchable.
    """
    return _read_dispatch_lock(
        path=dispatch_lock_path(repo=repo, work_item_id=work_item_id),
        work_item_id=work_item_id,
    )


def live_dispatch_lock(*, repo: Path, work_item_id: str) -> DispatchLock | None:
    lock = recorded_dispatch_lock(repo=repo, work_item_id=work_item_id)
    if lock is None or not _lock_holder_matches_pid(lock=lock):
        return None
    return lock


def _stale_dispatch_lock_reclaimed(*, path: Path, work_item_id: str) -> bool:
    opened = attempt(
        action=lambda: _reclaim_mutex_path(path=path).open("a+b"),
        exceptions=(OSError,),
    )
    if isinstance(opened, AttemptFailure):
        return False
    with opened as mutex:
        locked = attempt(
            action=lambda: fcntl.flock(mutex.fileno(), fcntl.LOCK_EX),
            exceptions=(OSError,),
        )
        if isinstance(locked, AttemptFailure):
            return False
        return _stale_dispatch_lock_reclaimed_locked(path=path, work_item_id=work_item_id)


def _stale_dispatch_lock_reclaimed_locked(*, path: Path, work_item_id: str) -> bool:
    lock = _read_dispatch_lock(path=path, work_item_id=work_item_id)
    if lock is None or _lock_holder_matches_pid(lock=lock):
        return False
    if _read_dispatch_lock(path=path, work_item_id=work_item_id) != lock:
        return False
    release_dispatch_lock(path=path)
    return True


def _reclaim_mutex_path(*, path: Path) -> Path:
    return path.with_name(f"{path.name}.reclaim")


def _read_dispatch_lock(*, path: Path, work_item_id: str) -> DispatchLock | None:
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return None
    parsed_raw = parse_json(text=read)
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, object]", parsed_raw)
    return _dispatch_lock_from_payload(payload=parsed, expected_work_item_id=work_item_id)


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


def _lock_holder_matches_pid(*, lock: DispatchLock) -> bool:
    started_at_epoch = _process_started_at_epoch(pid=lock.pid)
    probed = attempt(action=lambda: os.kill(lock.pid, 0), exceptions=(OSError,))
    if isinstance(probed, AttemptFailure) and isinstance(probed.error, ProcessLookupError):
        return False
    if _pid_start_time_mismatches(lock=lock, started_at_epoch=started_at_epoch):
        return False
    return not isinstance(probed, AttemptFailure)


def _pid_start_time_mismatches(*, lock: DispatchLock, started_at_epoch: float | None) -> bool:
    if started_at_epoch is None:
        return False
    return started_at_epoch > lock.started_at_epoch + _PROCESS_START_TOLERANCE_SECONDS


def _process_started_at_epoch(*, pid: int) -> float | None:
    return process_started_at_epoch(pid=pid)
