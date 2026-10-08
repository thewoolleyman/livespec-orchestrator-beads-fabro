"""Shared tier 1 live-run helpers for Fabro Enemy Unit Tests."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _FabroTier0Config,
    _mapping,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
)

__all__: list[str] = []

POLL_TIMEOUT_SECONDS = 180.0
POLL_INTERVAL_SECONDS = 2.0
# `recorded_at` is the Petri-era envelope field (measured 0.378.0-nightly.0);
# the three older names are what 0.254.0 emitted.
EVENT_TIMESTAMP_FIELDS = frozenset(("timestamp", "ts", "at", "recorded_at"))
EVENT_NAME_FIELDS = frozenset(("event", "event_name", "kind", "type"))


class _Plan:
    def __init__(self, *, work_item_id: str) -> None:
        self.work_item_id = work_item_id


def _write_workflow(*, tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.fabro"
    path.write_text(body.strip() + "\n")
    return path


def _write_goal(*, tmp_path: Path, title: str) -> Path:
    path = tmp_path / f"{title}-goal.md"
    path.write_text(f"# Fabro Enemy Unit Test: {title}\n")
    return path


def _terminal_outcome(
    *,
    config: _FabroTier0Config,
    inspect: FabroInspectResult,
    run_id: str,
    exit_code: int,
    stderr: str,
) -> DispatchOutcome | None:
    return fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_Plan(work_item_id=f"fabro-eut-{config.expected_client_commit}"),
        run_id=run_id,
        inspect=inspect,
        exit_code=exit_code,
        stderr=stderr,
    )


def _await_run_absent_from_ps(*, port: FabroPort, run_id: str) -> bool:
    """Return True once `run_id` is no longer listed by `fabro ps -a`.

    `fabro rm -f` removes a run from `ps -a` outright rather than leaving it
    with a terminated status (measured 0.254.0 / 8de6611), so the force-remove
    EUT waits for the run to disappear rather than for a status transition.
    """
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        ps = port.ps(timeout_seconds=TIMEOUT_SECONDS)
        _assert_success(command=ps.command)
        if all(summary.run_id != run_id for summary in ps.runs):
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


def _event_records(*, stdout: str, payload: object | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_mapping(value=item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [_mapping(value=item) for item in events if isinstance(item, dict)]
        return [cast("dict[str, Any]", payload)]
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if line.strip() == "":
            continue
        decoded = json.loads(line)
        if isinstance(decoded, dict):
            records.append(cast("dict[str, Any]", decoded))
    return records


def _has_event_timestamp(*, event: dict[str, Any]) -> bool:
    for key in EVENT_TIMESTAMP_FIELDS:
        value = event.get(key)
        if isinstance(value, str):
            return bool(value)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return True
    return False


def _event_name(*, event: dict[str, Any]) -> str | None:
    for key in EVENT_NAME_FIELDS:
        value = event.get(key)
        if isinstance(value, str) and value != "":
            return value
    return None


def _failure_block(*, value: object) -> dict[object, object] | None:
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        failure = mapping.get("failure")
        if isinstance(failure, dict):
            return cast("dict[object, object]", failure)
        for nested in mapping.values():
            block = _failure_block(value=nested)
            if block is not None:
                return block
    if isinstance(value, list):
        for nested in cast("list[object]", value):
            block = _failure_block(value=nested)
            if block is not None:
                return block
    return None
