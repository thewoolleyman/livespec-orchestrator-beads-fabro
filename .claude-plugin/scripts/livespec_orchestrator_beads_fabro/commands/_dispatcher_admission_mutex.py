"""Host-level dispatch admission cap (spec v047, bd-ib-sd8o deliverable (b)).

The counting successor of the interim binary admission mutex. Admission
capacity is measured by two INDEPENDENT host-global gauges, each capped by
`dispatcher.host_dispatch_cap` (never summed):

- gauge (ii), checked first: Fabro runs observed host-wide whose status is
  `running`. A PARKED (`blocked` / human_input_required) run never counts,
  terminal runs never count, and an unobservable `fabro ps` fails open (the
  slot gauge still bounds dispatcher-originated concurrency).
- gauge (i): capacity slot files `tmp/fabro-dispatch-admission.slot<i>.lock`
  for `i < cap`, one held per admitted dispatch from claim time until release.
  Each slot keeps the proven per-slot claim/release/crash-reclaim semantics:
  O_EXCL creation with a pid payload, a per-slot `.reclaim` flock with a
  double-read race guard, and dead-pid unlink so a crashed dispatcher's slot
  self-heals at a later claim attempt.

Reclaim notes: a transient flock failure on a dead-pid slot skips reclaim for
that attempt (the slot heals on a later attempt); a corrupt or unreadable slot
payload is NOT provably stale and reads as held ("no live pid recorded"); a
pid probe that raises EPERM reads as alive (the recycled-pid residual is
bd-ib-j4clfi, out of scope here).
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "AdmissionMutexClaim",
    "AdmissionMutexRefusal",
    "admission_mutex_slot_path",
    "claim_dispatch_admission_mutex",
    "release_dispatch_admission_mutex",
]

_FABRO_PS_TIMEOUT_SECONDS = 60.0
_GUARD_NAME = "dispatch admission cap"
_REMEDY = (
    "then retry, or raise livespec-orchestrator-beads-fabro.dispatcher."
    "host_dispatch_cap in .livespec.jsonc (config-only). This counting cap is "
    "the bd-ib-sd8o deliverable (b) demotion of the interim admission mutex.\n"
)


@dataclass(frozen=True, kw_only=True)
class AdmissionMutexClaim:
    path: Path


@dataclass(frozen=True, kw_only=True)
class AdmissionMutexRefusal:
    detail: str
    run_id: str | None


@dataclass(frozen=True, kw_only=True)
class _StoredAdmissionMutex:
    pid: int
    started_at_epoch: float | None
    guard: str | None


def admission_mutex_slot_path(*, repo: Path, slot: int) -> Path:
    return repo / "tmp" / f"fabro-dispatch-admission.slot{slot}.lock"


def claim_dispatch_admission_mutex(
    *, repo: Path, fabro_bin: str, runner: CommandRunner, cap: int
) -> AdmissionMutexClaim | AdmissionMutexRefusal:
    running = _running_run_ids(repo=repo, fabro_bin=fabro_bin, runner=runner)
    if len(running) >= cap:
        return _running_refusal(run_ids=running, cap=cap)
    admission_mutex_slot_path(repo=repo, slot=0).parent.mkdir(parents=True, exist_ok=True)
    for slot in range(cap):
        claimed = _claim_slot(path=admission_mutex_slot_path(repo=repo, slot=slot))
        if claimed is not None:
            return claimed
    return _contention_refusal(repo=repo, cap=cap)


def _claim_slot(*, path: Path) -> AdmissionMutexClaim | None:
    opened = _open_admission_mutex(path=path)
    if not isinstance(opened, AttemptFailure):
        _write_admission_mutex(descriptor=opened)
        return AdmissionMutexClaim(path=path)
    if not _stale_admission_mutex_reclaimed(path=path):
        return None
    opened = _open_admission_mutex(path=path)
    if not isinstance(opened, AttemptFailure):
        _write_admission_mutex(descriptor=opened)
        return AdmissionMutexClaim(path=path)
    return None


def _open_admission_mutex(*, path: Path) -> int | AttemptFailure:
    return attempt(
        action=lambda: os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        exceptions=(FileExistsError, OSError),
    )


def release_dispatch_admission_mutex(*, claim: AdmissionMutexClaim) -> None:
    _ = attempt(action=claim.path.unlink, exceptions=(FileNotFoundError, OSError))


def _running_run_ids(*, repo: Path, fabro_bin: str, runner: CommandRunner) -> list[str]:
    result = runner.run(
        argv=[fabro_bin, "ps", "-a", "--json"],
        cwd=repo,
        timeout_seconds=_FABRO_PS_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return []
    return _parse_running_run_ids(ps_json=result.stdout)


def _parse_running_run_ids(*, ps_json: str) -> list[str]:
    parsed_raw = parse_json(text=ps_json)
    if isinstance(parsed_raw, JsonParseFailure):
        return []
    running: list[str] = []
    for run_raw in _runs_list(parsed_raw=parsed_raw):
        if not isinstance(run_raw, dict):
            continue
        run = cast("dict[str, Any]", run_raw)
        if _run_status_kind(run=run) != "running":
            continue
        run_id_raw: object = run.get("run_id")
        if isinstance(run_id_raw, str) and run_id_raw:
            running.append(run_id_raw)
    return running


def _runs_list(*, parsed_raw: object) -> list[object]:
    if isinstance(parsed_raw, list):
        return cast("list[object]", parsed_raw)
    if isinstance(parsed_raw, dict):
        runs_raw: object = cast("dict[str, Any]", parsed_raw).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def _run_status_kind(*, run: dict[str, Any]) -> str | None:
    status_raw: object = run.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def _write_admission_mutex(*, descriptor: int) -> None:
    payload = {
        "guard": _GUARD_NAME,
        "pid": os.getpid(),
        "started_at_epoch": time.time(),
    }
    with os.fdopen(descriptor, "wb") as handle:
        _ = handle.write(json.dumps(payload, sort_keys=True).encode())
        _ = handle.write(b"\n")


def _stale_admission_mutex_reclaimed(*, path: Path) -> bool:
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
        return _stale_admission_mutex_reclaimed_locked(path=path)


def _stale_admission_mutex_reclaimed_locked(*, path: Path) -> bool:
    lock = _read_admission_mutex(path=path)
    if lock is None or _pid_is_alive(pid=lock.pid):
        return False
    if _read_admission_mutex(path=path) != lock:
        return False
    _ = attempt(action=path.unlink, exceptions=(FileNotFoundError, OSError))
    return True


def _reclaim_mutex_path(*, path: Path) -> Path:
    return path.with_name(f"{path.name}.reclaim")


def _read_admission_mutex(*, path: Path) -> _StoredAdmissionMutex | None:
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return None
    parsed_raw = attempt(
        action=lambda: json.loads(read), exceptions=(json.JSONDecodeError, TypeError)
    )
    if isinstance(parsed_raw, AttemptFailure) or not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, object]", parsed_raw)
    return _admission_mutex_from_payload(payload=parsed)


def _admission_mutex_from_payload(*, payload: dict[str, object]) -> _StoredAdmissionMutex | None:
    pid_raw = payload.get("pid")
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool) or pid_raw <= 0:
        return None
    started_raw = payload.get("started_at_epoch")
    started_at_epoch = (
        float(started_raw)
        if isinstance(started_raw, int | float) and not isinstance(started_raw, bool)
        else None
    )
    guard_raw = payload.get("guard")
    guard = guard_raw if isinstance(guard_raw, str) else None
    return _StoredAdmissionMutex(pid=pid_raw, started_at_epoch=started_at_epoch, guard=guard)


def _pid_is_alive(*, pid: int) -> bool:
    probed = attempt(action=lambda: os.kill(pid, 0), exceptions=(OSError,))
    if not isinstance(probed, AttemptFailure):
        return True
    return not isinstance(probed.error, ProcessLookupError)


def _running_refusal(*, run_ids: list[str], cap: int) -> AdmissionMutexRefusal:
    return AdmissionMutexRefusal(
        run_id=run_ids[0],
        detail=(
            f"ERROR: {_GUARD_NAME} refused this dispatch: {len(run_ids)} Fabro "
            f"run(s) already in flight ({', '.join(run_ids)}) meets the host "
            f"dispatch cap ({cap}). Wait for an in-flight run to reach "
            f"terminal state, {_REMEDY}"
        ),
    )


def _contention_refusal(*, repo: Path, cap: int) -> AdmissionMutexRefusal:
    details = "; ".join(
        _slot_detail(path=admission_mutex_slot_path(repo=repo, slot=slot), slot=slot)
        for slot in range(cap)
    )
    return AdmissionMutexRefusal(
        run_id=None,
        detail=(
            f"ERROR: {_GUARD_NAME} refused this dispatch: all {cap} admission "
            f"capacity slot(s) are held ({details}) while no terminal-state "
            f"release has been proven. Wait for a dispatch to release its "
            f"slot, {_REMEDY}"
        ),
    )


def _slot_detail(*, path: Path, slot: int) -> str:
    lock = _read_admission_mutex(path=path)
    if lock is None:
        return f"slot {slot}: no live pid recorded"
    return f"slot {slot}: pid {lock.pid}"
