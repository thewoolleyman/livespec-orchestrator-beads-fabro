"""Dispatcher auto-disposition decision journal helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "dispatcher_decision_journal_record",
    "read_dispatcher_decisions",
    "review_gate_ship_on_cap_journal_record",
]

_DECISION_STAGES = frozenset(
    (
        "ledger-approve",
        "ledger-accept",
        "acceptance-auto-rework",
        "review-gate-ship-on-cap",
        "acceptance-rework-cap-exceeded",
        "review-gate-cap-exceeded",
    )
)


def dispatcher_decision_journal_record(
    *,
    stage: str,
    work_item_id: str,
    disposition: str,
    governing_settings: Sequence[str],
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build one flat record for an automatic Dispatcher disposition."""
    record: dict[str, object] = {
        "stage": stage,
        "work_item_id": work_item_id,
        "disposition": disposition,
        "governing_settings": list(governing_settings),
    }
    if extra is not None:
        record.update(extra)
    return record


def review_gate_ship_on_cap_journal_record(
    *,
    work_item_id: str,
    run_id: str,
    review_verdict: str,
    review_fix_rounds: int,
    review_hit_cap: bool,
    pr_shipped_on_cap: bool,
) -> dict[str, object]:
    """Build the auto-disposition record for a review-cap ship."""
    return dispatcher_decision_journal_record(
        stage="review-gate-ship-on-cap",
        work_item_id=work_item_id,
        disposition="ship-on-cap",
        governing_settings=("merge_on_review_cap", "review_fix_cap"),
        extra={
            "run_id": run_id,
            "review_verdict": review_verdict,
            "review_fix_rounds": review_fix_rounds,
            "review_hit_cap": review_hit_cap,
            "pr_shipped_on_cap": pr_shipped_on_cap,
        },
    )


def read_dispatcher_decisions(*, journal_path: Path) -> tuple[dict[str, object], ...]:
    """Read auto-disposition records from the Dispatcher JSONL journal."""
    if not journal_path.is_file():
        return ()
    records: list[dict[str, object]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_json_object(line=line)
        if parsed is not None and _is_decision_record(record=parsed):
            records.append(parsed)
    return tuple(records)


def _parse_json_object(*, line: str) -> dict[str, object] | None:
    try:
        parsed: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    mapping = cast("dict[object, object]", parsed)
    return {str(key): value for key, value in mapping.items()}


def _is_decision_record(*, record: dict[str, object]) -> bool:
    stage = record.get("stage")
    work_item_id = record.get("work_item_id")
    disposition = record.get("disposition")
    governing_settings = record.get("governing_settings")
    if not isinstance(governing_settings, list):
        return False
    settings = cast("list[object]", governing_settings)
    return (
        isinstance(stage, str)
        and stage in _DECISION_STAGES
        and isinstance(work_item_id, str)
        and isinstance(disposition, str)
        and all(isinstance(setting, str) for setting in settings)
    )
