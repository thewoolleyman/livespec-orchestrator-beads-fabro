"""The aggregate model-fallback warning row, per node, from the newest record.

Binds the warning half of `SPECIFICATION/contracts.md` — cited at FILE level,
because a heading-level citation rots the moment the heading is reworded: "one
aggregate attention fact per repository/node with id
`hygiene:model-fallback:<repo>:<node>`", whose deterministic summary "the newest
unresolved observation supplies".

AGGREGATION IS THE CLAIM, so the fixture carries THREE observations across TWO
nodes and two of them share a node. One observation per node would be satisfied
by a lane that emitted a row per RECORD, which is the shape the contract's
"aggregate" forbids and the shape an operator would drown in; and the two
same-node observations differ in occurrence time, so "the newest supplies the
summary" can fail rather than hold by construction.

THIS MODULE WAS `test_acp_projection_surfaces.py`, and it lost its other two
subjects to the v127 retirement (`bd-ib-qm6r1`): the
`hygiene:model-fallback-projection` row and the clearance valve that retired it.
The lane's warning-only composition and the valve's absence are bound by
`test_needs_attention_model_fallback_warning_only.py`; what is HERE is the
surviving row's own aggregation, which that module asserts for one observation
and cannot assert for several.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    model_fallback_items,
)

_OCCURRED = "2026-09-12T12:00:00Z"
_REPO_NAME = "livespec-orchestrator-beads-fabro"


def _warning_line(
    *, node: str = "implement", occurred_at: str = _OCCURRED, key: str
) -> dict[str, Any]:
    return {
        "stage": "acp-model-fallback-observed",
        "schema_version": 1,
        "warning_id": f"acpwarn-{key}",
        "node": node,
        "occurred_at": occurred_at,
        "candidate_display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "event_id": f"ev-{key}",
        "candidate_index": 1,
        "work_item_id": "bd-ib-xtgwpz",
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _ids(*, items: list[Any]) -> list[str]:
    return [item.id for item in items]


def test_the_warning_row_aggregates_per_node_from_the_newest_observation(
    tmp_path: Path,
) -> None:
    """One row per node, and the NEWEST live observation supplies its summary."""
    _ = _journal(
        tmp_path=tmp_path,
        records=(
            _warning_line(key="older"),
            _warning_line(key="newest", occurred_at="2026-09-12T12:05:00Z"),
            _warning_line(node="pr", key="publish"),
        ),
    )
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert _ids(items=rows) == [
        f"hygiene:model-fallback:{_REPO_NAME}:implement",
        f"hygiene:model-fallback:{_REPO_NAME}:pr",
    ]
    implement = rows[0]
    assert implement.kind == "hygiene"
    assert implement.urgency in {"high", "medium", "low"}
    assert implement.source_ref.work_item == "bd-ib-xtgwpz"
    assert "display newest" in implement.summary
    assert "2 unresolved observations" in implement.summary
    assert implement.handoff.kind == "shell"
    assert "acp-model-fallback" in implement.handoff.command
    assert "implement" in implement.handoff.command


def test_a_warning_with_no_work_item_still_renders_a_row(tmp_path: Path) -> None:
    """Provenance is optional; the row is not."""
    line = _warning_line(key="anon")
    line["work_item_id"] = ""
    _ = _journal(tmp_path=tmp_path, records=(line,))
    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)
    assert rows[0].source_ref.work_item is None
    assert "1 unresolved" not in rows[0].summary
