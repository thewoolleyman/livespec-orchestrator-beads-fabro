"""The pre-claim `--acp-node` override check, isolated from the dispatch journey.

The end-to-end claim that a refused override leaves the item unclaimed on both
dispatch entry paths is bound at the integration tier by
`tests/integration/test_acp_override_refusal_before_claim.py`. These cases cover
the decisions that tier cannot isolate: the no-override and unreadable-workflow
pass-throughs, the per-item loop, and the journal row a refusal writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_acp_override_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import acp_override_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_override_wall import (
    ACP_OVERRIDE_REFUSAL_STAGE,
    acp_node_override_refusal,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_WORKFLOW = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\n'
    f'disposition_adapter = "{_CLAUDE}"\nreview_fix_adapter = "{_CLAUDE}"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n'
)


@pytest.fixture(autouse=True)
def _unrecorded_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every item previews the reserved variant, without a ledger read.

    The committed workflow is handed in through `--workflow`, which outranks the
    variant directory, so the preview's answer is irrelevant to what is graded.
    """
    monkeypatch.setattr(
        wall,
        "previewed_workflow_variant",
        lambda **_: SimpleNamespace(directory=None),
    )


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=item_id,
        description="override wall fixture",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    """A target whose `disposition` node is new-grammar-enabled."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "acp_nodes": {
                            "disposition": {
                                "agent": "codex-acp",
                                "model": "gpt-5.5",
                                "effort": "high",
                            }
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _committed(*, tmp_path: Path) -> Path:
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_WORKFLOW, encoding="utf-8")
    return committed


def _args(*, overrides: list[str] | None, committed: Path) -> argparse.Namespace:
    return argparse.Namespace(acp_node=overrides, workflow=str(committed), workflow_name=None)


def test_no_override_is_never_a_refusal(tmp_path: Path) -> None:
    """Without an override the resolution has nothing for this check to refuse."""
    repo = _repo(tmp_path=tmp_path)
    committed = _committed(tmp_path=tmp_path)
    journal = _Journal()

    assert acp_override_refusal(repo=repo, committed=committed, overrides=()) is None
    assert (
        acp_node_override_refusal(
            args=_args(overrides=None, committed=committed),
            repo=repo,
            items=[_item(item_id="bd-ib-none")],
            journal=journal,
        )
        is None
    )
    assert journal.records == []


def test_a_resolving_override_is_admitted_and_a_refused_one_is_journaled(tmp_path: Path) -> None:
    """The refusal names the item, journals one row, and stops at the first refusing item."""
    repo = _repo(tmp_path=tmp_path)
    committed = _committed(tmp_path=tmp_path)
    admitted = _Journal()
    ok = acp_node_override_refusal(
        args=_args(overrides=[f"review_fix={_CLAUDE}"], committed=committed),
        repo=repo,
        items=[_item(item_id="bd-ib-ok")],
        journal=admitted,
    )
    assert ok is None
    assert admitted.records == []

    journal = _Journal()
    refusal = acp_node_override_refusal(
        args=_args(overrides=[f"disposition={_CLAUDE}"], committed=committed),
        repo=repo,
        items=[_item(item_id="bd-ib-first"), _item(item_id="bd-ib-second")],
        journal=journal,
    )
    assert refusal is not None
    assert refusal.startswith("bd-ib-first: ")
    assert "legacy adapter string" in refusal
    [record] = journal.records
    assert record["stage"] == ACP_OVERRIDE_REFUSAL_STAGE
    assert record["work_item_id"] == "bd-ib-first"
    assert record["result"] == "refused"


def test_an_unreadable_workflow_is_left_to_the_stage_that_owns_it(tmp_path: Path) -> None:
    """A missing workflow config is not an override fault, so this row passes it through."""
    repo = _repo(tmp_path=tmp_path)
    journal = _Journal()

    result = acp_node_override_refusal(
        args=_args(overrides=[f"disposition={_CLAUDE}"], committed=tmp_path / "absent.toml"),
        repo=repo,
        items=[_item(item_id="bd-ib-absent")],
        journal=journal,
    )

    assert result is None
    assert journal.records == []


def test_the_wall_module_names_its_journal_stage() -> None:
    assert wall.ACP_OVERRIDE_REFUSAL_STAGE == "acp-node-override-refusal"
