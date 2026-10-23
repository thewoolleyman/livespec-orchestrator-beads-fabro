"""Coverage for the attention row an admission-required ACP chain's wait produces.

Binds the enumerated availability wait of `SPECIFICATION/contracts.md`, whose
wait-completeness clause among the orchestrator-owned attention facts reads:
"an item waiting because an admission-required ACP chain has no eligible
candidate ... likewise stays `ready`. The wait item MUST name the governing
condition and scheduled reevaluation instant."

EVERY FIXTURE HOLD EXPIRES IN THE FAR FUTURE, and that is what makes the rows
deterministic rather than merely stable-looking. `_reevaluate_at` is the
EARLIEST governing expiry whenever one parses, so a live hold fixes the
instant the row prints independently of when the pass runs -- which is the
ordinary shape of an availability wait, and the only shape under which two
real-clock passes can be compared for byte-identity at all.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_availability_wait.py"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_NAME = f"{_PACKAGE}._needs_attention_availability_wait"
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_FAR_FUTURE = "2099-01-01T00:15:00Z"
_LATER_STILL = "2099-01-01T00:45:00Z"

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_CHAIN = {
    "livespec-orchestrator-beads-fabro": {
        "dispatcher": {
            "acp_nodes": {
                "implement": {
                    "display_name": "Primary",
                    "candidate_key": "primary",
                    "availability_key": "codex",
                    "command": "adapter-primary",
                    "fallbacks": [
                        {
                            "display_name": "Fallback",
                            "candidate_key": "fallback",
                            "availability_key": "anthropic",
                            "command": "adapter-fallback",
                        }
                    ],
                }
            }
        }
    }
}


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title=f"{id_} title",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _hold(*, observation_id: str, hold_key: str, expires_at: str) -> dict[str, object]:
    return {
        "stage": "acp-availability-observed",
        "schema_version": 1,
        "observation_id": observation_id,
        "scope": "availability-domain",
        "hold_key": hold_key,
        "candidate_key": None,
        "cause": "quota",
        "occurred_at": "2026-09-12T11:50:00Z",
        "expires_at": expires_at,
    }


def _exhausted_repo(root: Path) -> Path:
    """A repository whose only ACP chain is emptied by two live domain holds."""
    workflow = root / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (root / ".livespec.jsonc").write_text(json.dumps(_CHAIN), encoding="utf-8")
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(
            json.dumps(record, sort_keys=True) + "\n"
            for record in (
                _hold(observation_id="obs-codex", hold_key="codex", expires_at=_LATER_STILL),
                _hold(observation_id="obs-anthropic", hold_key="anthropic", expires_at=_FAR_FUTURE),
            )
        ),
        encoding="utf-8",
    )
    return root


def _availability_wait_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(_MODULE_NAME)
    return module.availability_wait_items(**kwargs)


def test_the_wait_row_names_the_governing_condition_and_the_reevaluation_instant(
    tmp_path: Path,
) -> None:
    """The two facts the clause requires of the wait item, on one high-urgency row."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-waiting")]
    )

    assert [item.id for item in attention] == ["hygiene:acp-availability-wait:bd-waiting"]
    row = attention[0]
    assert row.kind == "hygiene"
    assert row.urgency == "high"
    assert row.source_ref.work_item == "bd-waiting"
    assert "governing_condition=typed-availability-hold" in row.summary
    # The earliest governing expiry, which is the first moment the situation
    # could change at all -- never the later hold's, and never a clock reading.
    assert f"scheduled_reevaluation_at={_FAR_FUTURE}" in row.summary


def test_a_viable_chain_composes_no_wait_row(tmp_path: Path) -> None:
    """Nothing is waiting, so nothing is reported: the row clears with the hold."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)
    (repo / _JOURNAL).write_text("", encoding="utf-8")

    assert _availability_wait_items(project_root=repo, repo="repo", items=[_item(id_="bd-x")]) == []


def test_only_ready_factory_safe_items_are_reported_as_waiting(tmp_path: Path) -> None:
    """A host-routed item and a non-ready item are not held by this wait."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)

    attention = _availability_wait_items(
        project_root=repo,
        repo="repo",
        items=[
            _item(id_="bd-host", factory_safety="host-only"),
            _item(id_="bd-backlog", status="backlog"),
            _item(id_="bd-ready"),
        ],
    )

    assert [item.source_ref.work_item for item in attention] == ["bd-ready"]
