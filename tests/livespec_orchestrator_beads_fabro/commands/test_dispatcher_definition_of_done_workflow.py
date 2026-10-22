"""The Definition-of-Done workflow-node admission gate.

The gate is intentionally exercised through the shared pre-dispatch wall as
well as directly.  A validator that found the right missing node after the
admission valve would still leave the item claimed, which is the failure this
gate prevents.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._workflow_variants import WorkflowVariant
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_workflow"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_definition_of_done_workflow.py"
)
_REQUIRED_NODES = ("dod_gate", "proof_capture", "proof_verify")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7k7re5",
        type="bug",
        status="ready",
        title="Workflow-node admission gate",
        description="Refuse an incomplete implement workflow before the claim.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatcher refuses an incomplete implement workflow.",
    )


def _write_workflow(*, root: Path, nodes: tuple[str, ...]) -> Path:
    workflow = root / ".fabro/workflows/implement-work-item"
    workflow.mkdir(parents=True)
    manifest = workflow / "workflow.toml"
    _ = manifest.write_text('[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8")
    declarations = "\n".join(f'{node} [label="{node}"]' for node in nodes)
    _ = (workflow / "workflow.fabro").write_text(
        f"digraph ImplementWorkItem {{\n{declarations}\n}}\n", encoding="utf-8"
    )
    return manifest


def _module() -> object:
    """Import the new validator only after a genuine, observable Red assertion."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), workflow=None, workflow_name=None)


@pytest.mark.parametrize("missing", _REQUIRED_NODES)
def test_each_missing_required_node_refuses_and_names_the_resolved_workflow_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing: str
) -> None:
    repo = tmp_path / "target"
    workflow = _write_workflow(
        root=repo, nodes=tuple(node for node in _REQUIRED_NODES if node != missing)
    )
    module = _module()
    monkeypatch.setattr(
        module,
        "previewed_workflow_variant",
        lambda **_kwargs: WorkflowVariant(name="implement-work-item", directory=None),
    )

    refusal = module.definition_of_done_workflow_refusal(
        args=_args(repo=repo), repo=repo, items=[_item()]
    )

    assert refusal is not None
    assert missing in refusal
    assert str(workflow) in refusal
    assert "no claim was taken" in refusal
    assert "no Fabro run was created" in refusal


def test_the_bundled_workflow_with_all_required_nodes_is_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "target"
    repo.mkdir()
    module = _module()
    monkeypatch.setattr(
        module,
        "previewed_workflow_variant",
        lambda **_kwargs: WorkflowVariant(name="implement-work-item", directory=None),
    )

    assert (
        module.definition_of_done_workflow_refusal(
            args=_args(repo=repo), repo=repo, items=[_item()]
        )
        is None
    )


def test_a_target_local_workflow_with_all_required_nodes_is_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "target"
    _ = _write_workflow(root=repo, nodes=_REQUIRED_NODES)
    module = _module()
    monkeypatch.setattr(
        module,
        "previewed_workflow_variant",
        lambda **_kwargs: WorkflowVariant(name="implement-work-item", directory=None),
    )

    assert (
        module.definition_of_done_workflow_refusal(
            args=_args(repo=repo), repo=repo, items=[_item()]
        )
        is None
    )


def test_the_shared_wall_returns_before_any_admission_or_later_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "target"
    _ = _write_workflow(root=repo, nodes=("dod_gate",))
    module = _module()
    monkeypatch.setattr(
        module,
        "previewed_workflow_variant",
        lambda **_kwargs: WorkflowVariant(name="implement-work-item", directory=None),
    )
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "fabro_currency_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "dod_judgement_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(
        wall,
        "selection_credential_requirement",
        lambda **_kwargs: pytest.fail("the wall reached a gate after the refusal"),
    )

    assert (
        wall.pre_dispatch_wall_exit(
            args=_args(repo=repo), repo=repo, items=[_item()], journal=object()
        )
        == 3
    )
