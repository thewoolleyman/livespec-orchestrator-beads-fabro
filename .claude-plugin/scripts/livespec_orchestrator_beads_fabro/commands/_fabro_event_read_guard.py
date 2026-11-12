"""Durable backoff and host-local concurrency for Fabro event reads."""

from __future__ import annotations

import fcntl
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroEventsResult

__all__: list[str] = [
    "FabroEventReadGuard",
    "FabroEventsReadRequest",
    "guarded_fabro_events_read",
]

_FAILURE_STAGE = "fabro-events-read-failed"
_SUCCESS_STAGE = "fabro-events-read-succeeded"
_INITIAL_BACKOFF_SECONDS = 60.0
_SLOT_COUNT = 2


class _Command(Protocol):
    exit_code: int
    stdout: str
    stderr: str


class _EventsResult(Protocol):
    command: _Command


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one dispatch-journal record."""


class _EventsPort(Protocol):
    def events(
        self, *, run_id: str, timeout_seconds: float, since: str | None = None
    ) -> FabroEventsResult:
        """Read one bounded Fabro event stream."""
        ...


@dataclass(frozen=True, kw_only=True)
class _ReadIdentity:
    work_item_id: str
    run_id: str
    factory: str
    caller: str


@dataclass(frozen=True, kw_only=True)
class FabroEventsReadRequest:
    """The caller-owned identity and timeout of one event-stream read."""

    work_item_id: str
    run_id: str
    factory: str
    caller: str
    timeout_seconds: float


@dataclass(kw_only=True)
class FabroEventReadGuard:
    """Prevent failed readers from repeatedly loading one factory stream."""

    journal: _Journal
    slots_root: Path
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _state_root: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._state_root = self.slots_root / "state"

    def read(
        self,
        *,
        work_item_id: str,
        run_id: str,
        factory: str,
        caller: str,
        timeout_seconds: float,
        read: Callable[[], object],
    ) -> _EventsResult | None:
        """Read once, or return ``None`` for a backed-off/unobservable read."""
        identity = _ReadIdentity(
            work_item_id=work_item_id,
            run_id=run_id,
            factory=factory,
            caller=caller,
        )
        state_path = self._state_path(
            factory=identity.factory,
            run_id=identity.run_id,
            caller=identity.caller,
        )
        state = self._read_state(path=state_path)
        started = self.clock()
        if started < state["next_read_at"]:
            return None
        slot = self._acquire_slot(factory=factory, timeout_seconds=timeout_seconds)
        if slot is None:
            return self._record_failure(
                identity=identity,
                elapsed_seconds=self.clock() - started,
                state_path=state_path,
                state=state,
            )
        try:
            result = cast(_EventsResult, read())
        finally:
            slot.close()
        if result.command.exit_code != 0 or result.command.stdout == "":
            return self._record_failure(
                identity=identity,
                elapsed_seconds=self.clock() - started,
                state_path=state_path,
                state=state,
            )
        state_path.unlink(missing_ok=True)
        self.journal.append(
            record={
                "stage": _SUCCESS_STAGE,
                "work_item_id": identity.work_item_id,
                "run_id": identity.run_id,
                "factory": identity.factory,
                "caller": identity.caller,
            }
        )
        return result

    def _record_failure(
        self,
        *,
        identity: _ReadIdentity,
        elapsed_seconds: float,
        state_path: Path,
        state: dict[str, float],
    ) -> None:
        attempt = state["attempt"] + 1.0
        backoff = _INITIAL_BACKOFF_SECONDS * (2.0 ** (attempt - 1.0))
        self._write_state(
            path=state_path,
            state={"attempt": attempt, "next_read_at": self.clock() + backoff},
        )
        self.journal.append(
            record={
                "stage": _FAILURE_STAGE,
                "work_item_id": identity.work_item_id,
                "run_id": identity.run_id,
                "factory": identity.factory,
                "caller": identity.caller,
                "elapsed_seconds": elapsed_seconds,
                "consecutive_attempt": int(attempt),
                "backoff_seconds": backoff,
            }
        )

    def _acquire_slot(self, *, factory: str, timeout_seconds: float) -> BinaryIO | None:
        deadline = self.clock() + timeout_seconds
        while True:
            for index in range(_SLOT_COUNT):
                path = self.slots_root / f"{_digest(factory)}-{index}.lock"
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open("a+b")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                return handle
            remaining = deadline - self.clock()
            if remaining <= 0:
                return None
            self.sleeper(min(remaining, 0.05))

    def _state_path(self, *, factory: str, run_id: str, caller: str) -> Path:
        return self._state_root / f"{_digest(factory, run_id, caller)}.json"

    def _read_state(self, *, path: Path) -> dict[str, float]:
        if not path.is_file():
            return {"attempt": 0.0, "next_read_at": 0.0}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "attempt": float(payload["attempt"]),
            "next_read_at": float(payload["next_read_at"]),
        }

    def _write_state(self, *, path: Path, state: dict[str, float]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(state), encoding="utf-8")


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def guarded_fabro_events_read(
    *,
    port: _EventsPort,
    journal: _Journal,
    slots_root: Path,
    request: FabroEventsReadRequest,
) -> FabroEventsResult | None:
    """Read one stream through the shared backoff and concurrency boundary."""
    guard = FabroEventReadGuard(journal=journal, slots_root=slots_root)
    result = guard.read(
        work_item_id=request.work_item_id,
        run_id=request.run_id,
        factory=request.factory,
        caller=request.caller,
        timeout_seconds=request.timeout_seconds,
        read=lambda: port.events(run_id=request.run_id, timeout_seconds=request.timeout_seconds),
    )
    return cast(FabroEventsResult | None, result)
