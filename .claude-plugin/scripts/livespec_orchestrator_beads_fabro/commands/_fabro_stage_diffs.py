"""Rebuild dump-compatible stage diff artifacts from a run-state projection.

The server's run-state projection holds the per-stage checkpoint diff beside
the event sequence that orders it.  Reading that projection avoids fetching a
run's event log, while materialising the familiar ``stages/<rank>-<stage>``
layout lets preserve-by-reference retain the exact artifact names and bytes a
full dump would have written.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = ["StageDiff", "stage_diffs_from_run_state", "write_stage_diffs"]


@dataclass(frozen=True, kw_only=True)
class StageDiff:
    """One dump-compatible stage diff, addressed by its export-relative path."""

    path: Path
    payload: str


def stage_diffs_from_run_state(*, run_state: object) -> tuple[StageDiff, ...]:
    """Return the readable stage diffs ordered exactly as a dump writes them."""
    if not isinstance(run_state, dict):
        return ()
    state = cast("dict[str, object]", run_state)
    stages = state.get("stages")
    if not isinstance(stages, dict):
        return ()
    stage_records = cast("dict[object, object]", stages)
    found: list[tuple[int, str, str]] = []
    for stage_name, stage in stage_records.items():
        if not isinstance(stage_name, str) or not isinstance(stage, dict):
            continue
        stage_record = cast("dict[str, object]", stage)
        sequence = stage_record.get("first_event_seq")
        diff = stage_record.get("diff")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or not isinstance(diff, str):
            continue
        found.append((sequence, stage_name, diff))
    return tuple(
        StageDiff(path=Path("stages") / f"{sequence:03d}-{stage_name}" / "diff.patch", payload=diff)
        for sequence, stage_name, diff in sorted(found)
    )


def write_stage_diffs(*, stage_diffs: tuple[StageDiff, ...], output_dir: Path) -> tuple[Path, ...]:
    """Materialise stage diffs beneath one temporary dump-compatible export."""
    artifacts: list[Path] = []
    for stage_diff in stage_diffs:
        artifact = output_dir / stage_diff.path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        _ = artifact.write_text(stage_diff.payload, encoding="utf-8")
        artifacts.append(artifact)
    return tuple(artifacts)
