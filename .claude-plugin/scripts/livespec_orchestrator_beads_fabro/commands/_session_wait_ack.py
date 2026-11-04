"""Receipt-only acknowledgement and retention for durable wait records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    read_wait_record,
    recorded_associations,
    wait_record_path,
    wait_store_lock,
    write_wait_record,
)

__all__: list[str] = [
    "AckFacts",
    "AckPublisher",
    "AckResult",
    "ack_wait",
]


@dataclass(frozen=True, kw_only=True)
class AckFacts:
    """What a receipt acknowledgement can say about the wait it discharged."""

    repository: str
    session_id: str
    wait_id: str
    at: float
    armed_at: float | None
    return_reason: str | None
    associations: dict[str, str]


class AckPublisher(Protocol):
    def acknowledged(self, *, facts: AckFacts) -> None: ...


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
    publisher: AckPublisher | None = None,
) -> AckResult:
    path = wait_record_path(wait_store_root=wait_store_root, wait_id=wait_id)
    with wait_store_lock(wait_store_root=wait_store_root):
        if not path.exists():
            return AckResult(wait_id=wait_id, status="not-found")
        loaded = read_wait_record(path=path)
        if loaded.payload is None:
            # The record EXISTS and cannot be understood, which is a different
            # fact from its absence and has a different remedy. Reporting it as
            # `not-found` would invite disposing of an outstanding obligation.
            return AckResult(wait_id=wait_id, status="unavailable")
        payload = loaded.payload
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
    if publisher is not None:
        publisher.acknowledged(
            facts=AckFacts(
                repository=str(payload["repository"]),
                session_id=session_id,
                wait_id=wait_id,
                at=acknowledged_at,
                armed_at=_instant(value=payload.get("armed_at")),
                return_reason=_text(value=payload.get("return_reason")),
                associations=recorded_associations(payload=payload),
            )
        )
    return AckResult(wait_id=wait_id, status="receipt-acknowledged")


def _instant(*, value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _text(*, value: object) -> str | None:
    return value if isinstance(value, str) else None
