"""Atomic persistence for host-session wait registrations and receipts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from livespec_orchestrator_beads_fabro.commands._dispatcher_pid_liveness import (
    process_started_at_epoch,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    run_with_wait_store_lock,
    wait_store_lock,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitRequest,
)

__all__: list[str] = [
    "DIAGNOSTIC_INVALID_RECORD",
    "DIAGNOSTIC_RECORD_DISPOSED",
    "DIAGNOSTIC_UNREADABLE_RECORD",
    "DIAGNOSTIC_UNSUPPORTED_SCHEMA",
    "REGISTRATION_CONFLICT",
    "REGISTRATION_REGISTERED",
    "REGISTRATION_UNAVAILABLE",
    "SCHEMA_VERSION",
    "WaitRecordRead",
    "WaiterIdentity",
    "current_waiter_identity",
    "process_generation_token",
    "read_wait_record",
    "record_observations",
    "record_return_ready",
    "register_wait",
    "wait_record_path",
    "wait_store_lock",
    "write_wait_record",
]

SCHEMA_VERSION = 1

DIAGNOSTIC_UNREADABLE_RECORD = "unreadable-record"
DIAGNOSTIC_INVALID_RECORD = "invalid-record"
DIAGNOSTIC_UNSUPPORTED_SCHEMA = "unsupported-schema"
DIAGNOSTIC_RECORD_DISPOSED = "record-disposed"

REGISTRATION_REGISTERED = "registered"
REGISTRATION_CONFLICT = "conflict"
REGISTRATION_UNAVAILABLE = "unavailable"

# Every field a version-1 record carries. A record missing or mistyping any of
# them is INVALID rather than partially usable: a consumer that defaulted one
# in would be inventing a deadline or an owner it never read.
_REQUIRED_FIELDS = frozenset(
    {
        "acknowledgement",
        "armed_at",
        "deadline_at",
        "deadline_seconds",
        "observation_sequence",
        "observations",
        "repository",
        "return_ready",
        "session_id",
        "targets",
        "wait_id",
        "waiter",
    }
)


@dataclass(frozen=True, kw_only=True)
class WaiterIdentity:
    pid: int
    generation: str


@dataclass(frozen=True, kw_only=True)
class WaitRecordRead:
    payload: dict[str, object] | None
    diagnostic: str | None


def current_waiter_identity() -> WaiterIdentity:
    pid = os.getpid()
    return WaiterIdentity(pid=pid, generation=str(process_generation_token(pid=pid)))


def process_generation_token(*, pid: int) -> str | None:
    started_at = process_started_at_epoch(pid=pid)
    return None if started_at is None else str(started_at)


def wait_record_path(*, wait_store_root: Path, wait_id: str) -> Path:
    return wait_store_root / f"{wait_id}.json"


def write_wait_record(*, path: Path, payload: dict[str, object]) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    _ = temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ = temporary.replace(path)


def read_wait_record(*, path: Path) -> WaitRecordRead:
    """Read one record, reporting every unusable shape as a diagnostic.

    This NEVER raises. A record that cannot be understood has to stay VISIBLE
    as a finding: an inventory pass that died on one corrupt file would take
    down the census that exists to surface it, and one that skipped the file
    silently would report a clean, plausible, incomplete answer. So each
    distinguishable failure gets its own diagnostic and no payload, and a
    payload that IS returned has been checked well enough for its consumers to
    index it.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return WaitRecordRead(payload=None, diagnostic=DIAGNOSTIC_UNREADABLE_RECORD)
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return WaitRecordRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    if not isinstance(loaded, dict):
        return WaitRecordRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    payload = cast("dict[str, object]", loaded)
    if payload.get("schema_version") != SCHEMA_VERSION:
        return WaitRecordRead(payload=None, diagnostic=DIAGNOSTIC_UNSUPPORTED_SCHEMA)
    if not _well_formed(payload=payload):
        return WaitRecordRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    return WaitRecordRead(payload=payload, diagnostic=None)


def _well_formed(*, payload: dict[str, object]) -> bool:
    """Whether a version-1 record carries every field at an indexable type."""
    return all(
        (
            payload.keys() >= _REQUIRED_FIELDS,
            isinstance(payload.get("acknowledgement"), dict),
            isinstance(payload.get("deadline_at"), float | int),
            isinstance(payload.get("observation_sequence"), int),
            isinstance(payload.get("observations"), list),
            isinstance(payload.get("return_ready"), bool),
            isinstance(payload.get("session_id"), str),
            isinstance(payload.get("targets"), list),
            isinstance(payload.get("wait_id"), str),
            isinstance(payload.get("waiter"), dict),
        )
    )


def register_wait(
    *,
    request: WaitRequest,
    wait_store_root: Path,
    waiter: WaiterIdentity,
    armed_at: float,
    lock_budget: LockBudget | None = None,
) -> str:
    path = wait_record_path(wait_store_root=wait_store_root, wait_id=request.wait_id)
    result = run_with_wait_store_lock(
        wait_store_root=wait_store_root,
        budget=lock_budget,
        action=lambda: _register_wait(
            path=path,
            request=request,
            waiter=waiter,
            armed_at=armed_at,
        ),
    )
    return REGISTRATION_UNAVAILABLE if result is None else result


def _register_wait(
    *, path: Path, request: WaitRequest, waiter: WaiterIdentity, armed_at: float
) -> str:
    if path.exists():
        return REGISTRATION_CONFLICT
    targets: list[dict[str, object]] = [
        {
            "generation": target.generation,
            "gate_store_root": str(target.gate_store_root),
            "identity": target.identity,
            "kind": "gate",
            "run_id": target.run_id,
        }
        for target in request.targets
    ]
    payload: dict[str, object] = {
        "acknowledgement": {
            "acknowledged": False,
            "acknowledged_at": None,
            "kind": None,
            "session_id": None,
        },
        "armed_at": armed_at,
        "deadline_at": armed_at + request.deadline_seconds,
        "deadline_seconds": request.deadline_seconds,
        "observation_sequence": 0,
        "observations": [],
        "repository": str(request.repository),
        "return_ready": False,
        "return_reason": None,
        "schema_version": SCHEMA_VERSION,
        "session_id": request.session_id,
        "targets": targets,
        "wait_id": request.wait_id,
        "waiter": {"generation": waiter.generation, "pid": waiter.pid},
    }
    write_wait_record(path=path, payload=payload)
    return REGISTRATION_REGISTERED


def _observation_payload(*, observation: GateObservation) -> dict[str, object]:
    return {
        "exit_code": observation.exit_code,
        "fresh": observation.fresh,
        "observed_at": observation.observed_at,
        "state": observation.state,
        "target": observation.target.identity,
    }


def record_observations(
    *,
    wait_store_root: Path,
    wait_id: str,
    observations: tuple[GateObservation, ...],
    lock_budget: LockBudget | None = None,
) -> bool:
    path = wait_record_path(wait_store_root=wait_store_root, wait_id=wait_id)
    result = run_with_wait_store_lock(
        wait_store_root=wait_store_root,
        budget=lock_budget,
        action=lambda: _record_observations(path=path, observations=observations),
    )
    # `is True`, not `is not None`: the lock helper reports an unacquired lock
    # as None, and the action reports a DISPOSED record as False. Reading only
    # for None would swallow the disposal the re-read exists to detect.
    return result is True


def _record_observations(*, path: Path, observations: tuple[GateObservation, ...]) -> bool:
    loaded = read_wait_record(path=path)
    if loaded.payload is None:
        return False
    payload = loaded.payload
    payload["observation_sequence"] = cast("int", payload["observation_sequence"]) + 1
    payload["observations"] = [
        _observation_payload(observation=observation) for observation in observations
    ]
    write_wait_record(path=path, payload=payload)
    return True


def record_return_ready(
    *,
    wait_store_root: Path,
    wait_id: str,
    return_reason: str,
    lock_budget: LockBudget | None = None,
) -> bool:
    path = wait_record_path(wait_store_root=wait_store_root, wait_id=wait_id)
    result = run_with_wait_store_lock(
        wait_store_root=wait_store_root,
        budget=lock_budget,
        action=lambda: _record_return_ready(
            path=path,
            return_reason=return_reason,
        ),
    )
    return result is True


def _record_return_ready(*, path: Path, return_reason: str) -> bool:
    loaded = read_wait_record(path=path)
    if loaded.payload is None:
        return False
    payload = loaded.payload
    payload["return_ready"] = True
    payload["return_reason"] = return_reason
    write_wait_record(path=path, payload=payload)
    return True
