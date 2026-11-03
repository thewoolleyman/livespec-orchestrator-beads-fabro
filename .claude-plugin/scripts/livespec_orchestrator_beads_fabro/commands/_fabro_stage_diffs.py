"""Selective reads of the stage diffs a Fabro dump writes verbatim.

`GET /api/v1/runs/<id>/state` returns the event-sourced run projection but not
its stream. The projection's private stage map serializes each stage's `diff`
field, and `fabro dump` writes that field unchanged as
`stages/<chronological-rank>-<stage-id>/diff.patch`. Keeping the projection's
ordering rule here makes the selective paths and bytes match a full dump
without materializing `events.jsonl`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort

__all__: list[str] = [
    "FabroStageDiff",
    "FabroStageDiffsUnreadable",
    "read_fabro_stage_diffs",
    "stage_diffs_from_run_state",
]

_READ_TIMEOUT_SECONDS = 300.0
_STAGES_KEY = "stages"
_FIRST_EVENT_SEQUENCE_KEY = "first_event_seq"
_DIFF_KEY = "diff"
_MAX_DUMP_STAGES = 999


@dataclass(frozen=True, kw_only=True)
class FabroStageDiff:
    """One dump-relative diff artifact and the UTF-8 bytes a dump writes."""

    path: str
    contents: bytes


@dataclass(frozen=True, kw_only=True)
class FabroStageDiffsUnreadable:
    """Why the selective state read cannot honestly supply stage diffs."""

    detail: str


def read_fabro_stage_diffs(
    *,
    port: FabroHttpPort,
    run_id: str,
    timeout_seconds: float = _READ_TIMEOUT_SECONDS,
) -> tuple[FabroStageDiff, ...] | FabroStageDiffsUnreadable:
    """Read only the run projection and extract its dump-equivalent diffs."""
    result = port.run_state(run_id=run_id, timeout_seconds=timeout_seconds)
    if not result.succeeded:
        return FabroStageDiffsUnreadable(
            detail=(
                f"the factory's selective stage-diff read for {run_id} returned status "
                f"{result.status}: {result.error or result.body.strip() or 'no body'}"
            )
        )
    return stage_diffs_from_run_state(payload=result.payload)


def stage_diffs_from_run_state(
    *, payload: object
) -> tuple[FabroStageDiff, ...] | FabroStageDiffsUnreadable:
    """Extract a full dump's stage-diff subset from one run-state payload."""
    if not isinstance(payload, dict):
        return FabroStageDiffsUnreadable(detail="the run-state response was not an object")
    state = cast("dict[object, object]", payload)
    stages = state.get(_STAGES_KEY)
    if not isinstance(stages, dict):
        return FabroStageDiffsUnreadable(
            detail="the run-state response carried no object-valued stages map"
        )
    stage_map = cast("dict[object, object]", stages)
    if len(stage_map) > _MAX_DUMP_STAGES:
        return FabroStageDiffsUnreadable(
            detail=f"the run-state response carries more than {_MAX_DUMP_STAGES} stages"
        )
    parsed: list[tuple[int, str, str | None]] = []
    for stage_id, stage in stage_map.items():
        entry = _stage_entry(stage_id=stage_id, stage=stage)
        if isinstance(entry, FabroStageDiffsUnreadable):
            return entry
        parsed.append(entry)
    return tuple(
        FabroStageDiff(
            path=f"stages/{rank:03d}-{stage_id}/diff.patch",
            contents=diff.encode("utf-8"),
        )
        for rank, (_, stage_id, diff) in enumerate(sorted(parsed), start=1)
        if diff is not None
    )


def _stage_entry(
    *, stage_id: object, stage: object
) -> tuple[int, str, str | None] | FabroStageDiffsUnreadable:
    if not isinstance(stage_id, str) or not _is_stage_id(value=stage_id):
        return FabroStageDiffsUnreadable(detail="a run-state stage id was not a node@visit string")
    if not isinstance(stage, dict):
        return FabroStageDiffsUnreadable(detail=f"the run-state stage {stage_id} was not an object")
    mapping = cast("dict[object, object]", stage)
    sequence = mapping.get(_FIRST_EVENT_SEQUENCE_KEY)
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        return FabroStageDiffsUnreadable(
            detail=f"the run-state stage {stage_id} carried no positive first_event_seq"
        )
    diff = mapping.get(_DIFF_KEY)
    if diff is not None and not isinstance(diff, str):
        return FabroStageDiffsUnreadable(
            detail=f"the run-state stage {stage_id} carried a non-string diff"
        )
    return (sequence, stage_id, diff)


def _is_stage_id(*, value: str) -> bool:
    node, separator, visit = value.rpartition("@")
    return bool(node) and separator == "@" and visit.isdecimal() and int(visit) > 0
