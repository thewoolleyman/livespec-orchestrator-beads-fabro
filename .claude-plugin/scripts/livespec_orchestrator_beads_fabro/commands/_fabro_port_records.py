"""Fabro response records owned by the dispatcher Fabro port."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "FabroRunSummary",
    "fabro_inspect_record",
    "fabro_run_id_from_output",
    "fabro_run_summaries_from_payload",
    "fabro_run_summaries_from_stdout",
    "fabro_status_kind_from_payload",
]

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")
_WORK_ITEM_RE = re.compile(r"^Work-item:\s*(\S+)", re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class FabroRunSummary:
    """Run row from `fabro ps -a --json` that livespec code reads."""

    run_id: str
    status_kind: str | None
    goal: str | None
    total_usd_micros: int | None
    work_item_id: str | None = field(default=None, compare=False)


def fabro_run_id_from_output(*, output: str) -> str | None:
    plain = _ANSI_ESCAPE_RE.sub("", output)
    match = _RUN_ID_RE.search(plain)
    if match is None:
        return None
    return match.group(1)


def fabro_run_summaries_from_stdout(*, stdout: str) -> tuple[FabroRunSummary, ...]:
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return ()
    return fabro_run_summaries_from_payload(payload=parsed)


def fabro_run_summaries_from_payload(*, payload: object | None) -> tuple[FabroRunSummary, ...]:
    summaries: list[FabroRunSummary] = []
    for run in _runs(payload=payload):
        summary = _run_summary(run=run)
        if summary is not None:
            summaries.append(summary)
    return tuple(summaries)


def fabro_inspect_record(*, payload: object | None) -> dict[str, Any] | None:
    """Normalize an `inspect` payload to the single run record it describes.

    `fabro inspect <run> --json` returns a single-element LIST on the pinned
    build (0.254.0), not a bare mapping. Measured against six real payloads on
    2026-08-20. Mapping payloads are still accepted so a future shape change
    back to a bare object does not regress.
    """
    if isinstance(payload, dict):
        return cast("dict[str, Any]", payload)
    if isinstance(payload, list):
        for entry in cast("list[object]", payload):
            if isinstance(entry, dict):
                return cast("dict[str, Any]", entry)
    return None


def fabro_status_kind_from_payload(*, payload: object | None) -> str | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    status_raw: object = record.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def _runs(*, payload: object | None) -> list[object]:
    if isinstance(payload, list):
        return cast("list[object]", payload)
    if isinstance(payload, dict):
        runs_raw: object = cast("dict[str, Any]", payload).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def _run_summary(*, run: object) -> FabroRunSummary | None:
    if not isinstance(run, dict):
        return None
    record = cast("dict[str, Any]", run)
    run_id_raw: object = record.get("run_id")
    if not isinstance(run_id_raw, str) or run_id_raw == "":
        return None
    goal = _optional_str(value=record.get("goal"))
    return FabroRunSummary(
        run_id=run_id_raw,
        status_kind=fabro_status_kind_from_payload(payload=record),
        goal=goal,
        work_item_id=_work_item_id(goal=goal),
        total_usd_micros=_optional_int(value=record.get("total_usd_micros")),
    )


def _optional_str(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(*, value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _work_item_id(*, goal: str | None) -> str | None:
    if goal is None:
        return None
    match = _WORK_ITEM_RE.search(goal)
    return None if match is None else match.group(1)
