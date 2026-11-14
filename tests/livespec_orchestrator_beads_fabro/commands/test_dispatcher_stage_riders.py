"""Stage-targeted dispatch rider briefs (Scenario 268)."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts
from livespec_orchestrator_beads_fabro.store import WorkItemComment

_STAGE_RIDERS_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_stage_riders"
_PAYLOAD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_payload_stage_riders"


def _module(*, name: str) -> ModuleType:
    package = importlib.import_module("livespec_orchestrator_beads_fabro")
    expected = Path(package.__file__ or "").parent / "commands" / f"{name}.py"
    assert expected.is_file(), f"{expected} does not exist yet"
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{name}")


def _comment(*, text: str) -> WorkItemComment:
    return WorkItemComment(text=text, author="operator", created_at="2026-11-12T00:00:00Z")


def _workflow(*, tmp_path: Path, stages: tuple[str, ...]) -> Path:
    workflow = tmp_path / "workflow"
    prompts = workflow / "prompts"
    prompts.mkdir(parents=True)
    for stage in stages:
        _ = (prompts / f"{stage}.md").write_text(f"{stage} prompt\n", encoding="utf-8")
    _ = (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8"
    )
    nodes = "".join(f'{stage} [timeout="1800s" prompt="@prompts/{stage}.md"]\n' for stage in stages)
    _ = (workflow / "workflow.fabro").write_text(
        f'digraph G {{\ngraph [stall_timeout="7200s"]\n{nodes}}}\n', encoding="utf-8"
    )
    return workflow


def test_riders_reach_only_their_named_stage_or_the_tree_changing_default(
    tmp_path: Path,
) -> None:
    stage_riders = _module(name="_dispatcher_stage_riders")
    payload_riders = _module(name="_dispatcher_payload_stage_riders")
    sections = stage_riders.stage_rider_sections(
        comments=(
            _comment(text="FOR implement ONLY: IMPLEMENT-RIDER"),
            _comment(text="FOR review_fix ONLY: REVIEW-FIX-RIDER"),
            _comment(text="UNSCOPED-RIDER"),
            _comment(text="STANDING RIDER: STANDING-RIDER"),
        ),
        claim_at=None,
    )

    assert "IMPLEMENT-RIDER" in sections["implement"]
    assert "IMPLEMENT-RIDER" not in sections["review"]
    assert "IMPLEMENT-RIDER" not in sections["proof_capture"]
    assert "IMPLEMENT-RIDER" not in sections["proof_verify"]
    assert "REVIEW-FIX-RIDER" in sections["review_fix"]
    assert "UNSCOPED-RIDER" in sections["implement"]
    assert "UNSCOPED-RIDER" in sections["review_fix"]
    assert "UNSCOPED-RIDER" not in sections["review"]
    assert "UNSCOPED-RIDER" not in sections["proof_capture"]
    assert "UNSCOPED-RIDER" not in sections["proof_verify"]
    assert "STANDING-RIDER" in sections["review"]
    assert "STANDING-RIDER" in sections["proof_capture"]
    assert "STANDING-RIDER" in sections["proof_verify"]

    workflow = _workflow(
        tmp_path=tmp_path,
        stages=("implement", "review_fix", "review", "proof_capture", "proof_verify"),
    )
    payload = materialize_workflow_payload(
        committed=workflow / "workflow.toml",
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )

    assert isinstance(payload, WorkflowPayload)
    assert (
        payload_riders.prefix_stage_riders(
            payload_dir=payload.payload_dir,
            graph=payload.graph,
            stage_riders=sections,
        )
        is None
    )
    assert "IMPLEMENT-RIDER" in (payload.payload_dir / "prompts" / "implement.md").read_text(
        encoding="utf-8"
    )
    assert "REVIEW-FIX-RIDER" in (payload.payload_dir / "prompts" / "review_fix.md").read_text(
        encoding="utf-8"
    )
    for stage in ("review", "proof_capture", "proof_verify"):
        prompt = (payload.payload_dir / "prompts" / f"{stage}.md").read_text(encoding="utf-8")
        assert "IMPLEMENT-RIDER" not in prompt
        assert "REVIEW-FIX-RIDER" not in prompt
