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

__all__: list[str] = [
    "DEFAULT_DEFER_COLLECTION_WHILE_ACTIVE",
    "DEFAULT_RM_MIN_INTERVAL_SECONDS",
    "DeletionPacer",
]

DEFAULT_DEFER_COLLECTION_WHILE_ACTIVE = True
DEFAULT_RM_MIN_INTERVAL_SECONDS = 60
_DEFER_STAGE = "fabro-rm-deferred"


@dataclass(frozen=True, kw_only=True)
class _Settings:
    defer_collection_while_active: bool
    rm_min_interval_seconds: float


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


@dataclass(kw_only=True)
class DeletionPacer:
    """Authorize one deletion start, journaling any intentional deferral."""

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
        if has_running_run and collection and settings.defer_collection_while_active:
            _deferred(
                journal=journal,
                factory=factory,
                run_id=run_id,
                caller=caller,
                next_start=now,
            )
            return False
        if not has_running_run or settings.rm_min_interval_seconds == 0:
            return True
        path = _state_path(repo=self.repo, factory=factory)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as state:
            _ = fcntl.flock(state.fileno(), fcntl.LOCK_EX)
            previous = _previous_start(state=state)
            earliest = now if previous is None else previous + settings.rm_min_interval_seconds
            if now < earliest:
                _deferred(
                    journal=journal,
                    factory=factory,
                    run_id=run_id,
                    caller=caller,
                    next_start=earliest,
                )
                return False
            _ = state.seek(0)
            _ = state.truncate()
            _ = state.write(json.dumps({"started_at": now}) + "\n")
            state.flush()
        return True


def _settings(*, repo: Path, factory: str) -> _Settings:
    factories_raw: object = dispatcher_block(cwd=repo).get("factories")
    factories = (
        cast("dict[str, object]", factories_raw) if isinstance(factories_raw, dict) else None
    )
    entry: object = factories.get(factory) if factories is not None else None
    configured: dict[str, object] = (
        cast("dict[str, object]", entry) if isinstance(entry, dict) else {}
    )
    defer = configured.get("defer_collection_while_active")
    interval = configured.get("rm_min_interval_seconds")
    return _Settings(
        defer_collection_while_active=(
            defer if isinstance(defer, bool) else DEFAULT_DEFER_COLLECTION_WHILE_ACTIVE
        ),
        rm_min_interval_seconds=(
            float(interval)
            if (
                isinstance(interval, int | float)
                and not isinstance(interval, bool)
                and interval >= 0
            )
            else float(DEFAULT_RM_MIN_INTERVAL_SECONDS)
        ),
    )


def _state_path(*, repo: Path, factory: str) -> Path:
    identity = hashlib.sha256(f"{_repo_identity(repo=repo)}:{factory}".encode()).hexdigest()
    return Path(tempfile.gettempdir()) / "livespec-fabro-rm-pacing" / f"{identity}.json"


def _repo_identity(*, repo: Path) -> str:
    git_entry = repo / ".git"
    if git_entry.is_dir():
        return str(git_entry.resolve())
    if git_entry.is_file():
        try:
            first_line = git_entry.read_text(encoding="utf-8").splitlines()[0]
        except (IndexError, OSError):
            return str(repo.resolve())
        prefix = "gitdir: "
        if first_line.startswith(prefix):
            worktree_gitdir = Path(first_line.removeprefix(prefix)).resolve()
            if worktree_gitdir.parent.name == "worktrees":
                return str(worktree_gitdir.parent.parent.resolve())
    return str(repo.resolve())


def _previous_start(*, state: TextIO) -> float | None:
    _ = state.seek(0)
    try:
        payload: object = json.loads(state.read())
    except json.JSONDecodeError:
        return None
    parsed = cast("dict[str, object]", payload) if isinstance(payload, dict) else None
    value: object = parsed.get("started_at") if parsed is not None else None
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _deferred(
    *,
    journal: list[dict[str, object]] | _Journal,
    factory: str,
    run_id: str,
    caller: str,
    next_start: float,
) -> None:
    record: dict[str, object] = {
        "stage": _DEFER_STAGE,
        "run_id": run_id,
        "factory": factory,
        "caller": caller,
        "next_deletion_may_start_at": next_start,
    }
    if isinstance(journal, list):
        journal.append(record)
    else:
        journal.append(record=record)
