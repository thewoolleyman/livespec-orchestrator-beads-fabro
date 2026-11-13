"""Host-wide pacing for destructive Fabro run deletions."""

from __future__ import annotations

import fcntl
import hashlib
import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = ["DeletionPacer", "previous_start"]

_DEFAULT_DEFER_COLLECTION_WHILE_ACTIVE = True
_DEFAULT_RM_MIN_INTERVAL_SECONDS = 60.0
_DEFERRED_STAGE = "fabro-rm-deferred"


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


@dataclass(frozen=True, kw_only=True)
class _Settings:
    defer_collection_while_active: bool
    minimum_interval_seconds: float


@dataclass(kw_only=True)
class DeletionPacer:
    """Permit a deletion start or journal its intentional deferral."""

    repo: Path
    now_epoch: Callable[[], float] = time.time

    def permit(
        self,
        *,
        factory: str,
        run_id: str,
        caller: str,
        has_running_run: bool,
        collection: bool,
        journal: list[dict[str, object]] | _Journal,
    ) -> bool:
        settings = _settings(repo=self.repo, factory=factory)
        now = self.now_epoch()
        if collection and has_running_run and settings.defer_collection_while_active:
            _journal_deferred(
                journal=journal, factory=factory, run_id=run_id, caller=caller, next_start=now
            )
            return False
        if not has_running_run or settings.minimum_interval_seconds == 0:
            return True
        state_path = _state_path(factory=factory)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("a+", encoding="utf-8") as state:
            _ = fcntl.flock(state.fileno(), fcntl.LOCK_EX)
            previous = previous_start(state=state)
            next_start = now if previous is None else previous + settings.minimum_interval_seconds
            if now < next_start:
                _journal_deferred(
                    journal=journal,
                    factory=factory,
                    run_id=run_id,
                    caller=caller,
                    next_start=next_start,
                )
                return False
            _ = state.seek(0)
            _ = state.truncate()
            _ = state.write(json.dumps({"started_at": now}))
            state.flush()
        return True


def _settings(*, repo: Path, factory: str) -> _Settings:
    factories_raw = dispatcher_block(cwd=repo).get("factories")
    factories = cast("dict[str, object]", factories_raw) if isinstance(factories_raw, dict) else {}
    raw = factories.get(factory)
    configured = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    defer = configured.get("defer_collection_while_active")
    interval = configured.get("rm_min_interval_seconds")
    return _Settings(
        defer_collection_while_active=(
            defer if isinstance(defer, bool) else _DEFAULT_DEFER_COLLECTION_WHILE_ACTIVE
        ),
        minimum_interval_seconds=(
            float(interval)
            if isinstance(interval, int | float)
            and not isinstance(interval, bool)
            and interval >= 0
            else _DEFAULT_RM_MIN_INTERVAL_SECONDS
        ),
    )


def _state_path(*, factory: str) -> Path:
    digest = hashlib.sha256(factory.encode()).hexdigest()
    return Path(tempfile.gettempdir()) / "livespec-fabro-rm-pacing" / f"{digest}.json"


def previous_start(*, state: TextIO) -> float | None:
    """Read the last reserved deletion instant from a pacing state file."""
    _ = state.seek(0)
    try:
        payload: object = json.loads(state.read())
    except json.JSONDecodeError:
        return None
    record = cast("dict[str, object]", payload) if isinstance(payload, dict) else {}
    value = record.get("started_at")
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _journal_deferred(
    *,
    journal: list[dict[str, object]] | _Journal,
    factory: str,
    run_id: str,
    caller: str,
    next_start: float,
) -> None:
    record: dict[str, object] = {
        "stage": _DEFERRED_STAGE,
        "run_id": run_id,
        "factory": factory,
        "caller": caller,
        "next_deletion_may_start_at": next_start,
    }
    if isinstance(journal, list):
        journal.append(record)
        return
    journal.append(record=record)
