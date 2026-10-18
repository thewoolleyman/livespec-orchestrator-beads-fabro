"""Journal-scan helpers for dispatcher reflection."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "items_with_retries",
    "items_with_run_turn_absence",
    "items_with_sizing_warn",
    "items_with_timeout",
    "read_journal_records",
    "trailing_green_streak",
]

_TIMEOUT_EXIT_CODE = 124
_RETRY_PR_VIEW_THRESHOLD = 2


class OutcomeLike(Protocol):
    @property
    def status(self) -> str: ...


def read_journal_records(*, journal_path: Path | None) -> tuple[dict[str, object], ...]:
    """Read back the append-only journal file as parsed records.

    `None` is accepted and answers the empty tuple, which is the same tolerance
    `_acp_journal_records.journal_records` and `_dispatcher_provider_exhaustion`
    already carry for this exact input: an IN-MEMORY journal has no file, and a
    reader asking one where its history lives must get "none to offer" rather
    than an `AttributeError` from a caller that had no way to know.
    """
    if journal_path is None or not journal_path.is_file():
        return ()
    records: list[dict[str, object]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_json(text=line)
        if isinstance(parsed, JsonParseFailure):
            continue
        if isinstance(parsed, dict):
            mapping = cast("dict[object, object]", parsed)
            typed: dict[str, object] = {str(key): value for key, value in mapping.items()}
            records.append(typed)
    return tuple(records)


def items_with_timeout(*, records: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    ids: list[str] = []
    for rec in records:
        if rec.get("exit_code") == _TIMEOUT_EXIT_CODE:
            item = rec.get("work_item_id")
            if isinstance(item, str) and item not in ids:
                ids.append(item)
    return tuple(ids)


def items_with_retries(*, records: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    """Items whose journal carries a repeated stage (poll re-views / retries)."""
    per_item_stage_counts: dict[str, dict[str, int]] = {}
    for rec in records:
        item = rec.get("work_item_id")
        stage = rec.get("stage")
        if not isinstance(item, str) or not isinstance(stage, str):
            continue
        counts = per_item_stage_counts.setdefault(item, {})
        counts[stage] = counts.get(stage, 0) + 1
    ids: list[str] = []
    for item, counts in per_item_stage_counts.items():
        updated_branch = counts.get("pr-update-branch", 0) >= 1
        repeated_view = counts.get("pr-view", 0) >= _RETRY_PR_VIEW_THRESHOLD
        if updated_branch or repeated_view:
            ids.append(item)
    return tuple(ids)


def items_with_sizing_warn(*, records: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    ids: list[str] = []
    for rec in records:
        if rec.get("stage") == "sizing-warn":
            item = rec.get("work_item_id")
            if isinstance(item, str) and item not in ids:
                ids.append(item)
    return tuple(ids)


def items_with_run_turn_absence(*, records: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    ids: list[str] = []
    for rec in records:
        if rec.get("stage") != "run-turn-telemetry-check":
            continue
        if rec.get("run_turn_observable") is False:
            continue
        if rec.get("run_turn_exported") is not False:
            continue
        item = rec.get("work_item_id")
        if isinstance(item, str) and item not in ids:
            ids.append(item)
    return tuple(ids)


def trailing_green_streak(*, outcomes: tuple[OutcomeLike, ...]) -> int:
    """The count of trailing consecutive green outcomes (gate-streak signal)."""
    streak = 0
    for outcome in reversed(outcomes):
        if outcome.status != "green":
            break
        streak += 1
    return streak
