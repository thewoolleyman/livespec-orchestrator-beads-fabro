"""Receipt-only acknowledgement and retention for durable wait records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    read_wait_record,
    wait_record_path,
    wait_store_lock,
    write_wait_record,
)

__all__: list[str] = [
    "AckResult",
    "ack_wait",
]


@dataclass(frozen=True, kw_only=True)
class AckResult:
    wait_id: str
    status: str


def _acknowledged_records(*, wait_store_root: Path) -> list[tuple[float, Path]]:
    acknowledged: list[tuple[float, Path]] = []
    for path in wait_store_root.glob("*.json"):
        loaded = read_wait_record(path=path)
        if loaded.payload is None:
            continue
        acknowledgement = cast("dict[str, object]", loaded.payload["acknowledgement"])
        if bool(acknowledgement["acknowledged"]):
            acknowledged.append((float(str(acknowledgement["acknowledged_at"])), path))
    return sorted(acknowledged)


def ack_wait(
    *,
    wait_store_root: Path,
    wait_id: str,
    session_id: str,
    acknowledged_at: float,
    retention_limit: int,
) -> AckResult:
    path = wait_record_path(wait_store_root=wait_store_root, wait_id=wait_id)
    with wait_store_lock(wait_store_root=wait_store_root):
        if not path.exists():
            return AckResult(wait_id=wait_id, status="not-found")
        payload = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        if payload["session_id"] != session_id:
            return AckResult(wait_id=wait_id, status="owner-mismatch")
        payload["acknowledgement"] = {
            "acknowledged": True,
            "acknowledged_at": acknowledged_at,
            "kind": "receipt-only",
            "session_id": session_id,
        }
        write_wait_record(path=path, payload=payload)
        acknowledged = _acknowledged_records(wait_store_root=wait_store_root)
        for _, expired in acknowledged[:-retention_limit]:
            expired.unlink()
    return AckResult(wait_id=wait_id, status="receipt-acknowledged")
