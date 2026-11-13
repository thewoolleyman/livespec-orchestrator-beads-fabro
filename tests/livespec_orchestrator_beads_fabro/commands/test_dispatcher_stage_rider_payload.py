"""Payload delivery of stage-targeted rider sections."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload_stage_riders import (
    prefix_stage_riders,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stage_riders import (
    stage_rider_sections,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts
from livespec_orchestrator_beads_fabro.store import WorkItemComment


def test_payload_prefixes_only_the_named_stage_prompt(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow"
    prompts = workflow / "prompts"
    prompts.mkdir(parents=True)
    _ = (prompts / "implement.md").write_text("implement prompt\n", encoding="utf-8")
    _ = (prompts / "review.md").write_text("review prompt\n", encoding="utf-8")
    _ = (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8"
    )
    _ = (workflow / "workflow.fabro").write_text(
        "".join(
            (
                "digraph G {\n",
                'graph [stall_timeout="7200s"]\n',
                'implement [timeout="1800s" prompt="@prompts/implement.md"]\n',
                'review [timeout="1800s" prompt="@prompts/review.md"]\n',
                "}\n",
            )
        ),
        encoding="utf-8",
    )

    payload = materialize_workflow_payload(
        committed=workflow / "workflow.toml",
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )

    assert isinstance(payload, WorkflowPayload)
    assert (
        prefix_stage_riders(
            payload_dir=payload.payload_dir,
            graph=payload.graph,
            stage_riders={"implement": "IMPLEMENT-RIDER\n", "review": ""},
        )
        is None
    )
    assert (
        (payload.payload_dir / "prompts" / "implement.md")
        .read_text(encoding="utf-8")
        .startswith("IMPLEMENT-RIDER\n")
    )
    assert (payload.payload_dir / "prompts" / "review.md").read_text(
        encoding="utf-8"
    ) == "review prompt\n"


def test_payload_ignores_a_rider_stage_the_workflow_does_not_declare(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow"
    prompts = workflow / "prompts"
    prompts.mkdir(parents=True)
    _ = (prompts / "review.md").write_text("review prompt\n", encoding="utf-8")
    _ = (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8"
    )
    _ = (workflow / "workflow.fabro").write_text(
        "".join(
            (
                "digraph G {\n",
                'graph [stall_timeout="7200s"]\n',
                'review [timeout="1800s" prompt="@prompts/review.md"]\n',
                "}\n",
            )
        ),
        encoding="utf-8",
    )

    payload = materialize_workflow_payload(
        committed=workflow / "workflow.toml",
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )

    assert isinstance(payload, WorkflowPayload)
    assert (
        prefix_stage_riders(
            payload_dir=payload.payload_dir,
            graph=payload.graph,
            stage_riders={"implement": "IMPLEMENT-RIDER\n", "review": "REVIEW-RIDER\n"},
        )
        is None
    )
    assert (
        (payload.payload_dir / "prompts" / "review.md")
        .read_text(encoding="utf-8")
        .startswith("REVIEW-RIDER\n")
    )


def test_payload_refuses_a_declared_stage_without_its_prompt(tmp_path: Path) -> None:
    graph = tmp_path / "workflow.fabro"
    _ = graph.write_text(
        'digraph G {\nimplement [prompt="@prompts/implement.md"]\n}\n', encoding="utf-8"
    )

    assert (
        prefix_stage_riders(
            payload_dir=tmp_path / "payload",
            graph=graph,
            stage_riders={"implement": "IMPLEMENT-RIDER\n"},
        )
        == "workflow prompt prompts/implement.md for stage implement is missing"
    )


def test_payload_refuses_a_declared_stage_without_a_prompt_attribute(tmp_path: Path) -> None:
    graph = tmp_path / "workflow.fabro"
    _ = graph.write_text(
        'digraph G {\nimplement [timeout="1800s"]\nreview [prompt="@prompts/review.md"]\n}\n',
        encoding="utf-8",
    )

    assert (
        prefix_stage_riders(
            payload_dir=tmp_path / "payload",
            graph=graph,
            stage_riders={"implement": "IMPLEMENT-RIDER\n"},
        )
        == 'workflow stage implement declares no prompt="@..." attribute for its rider'
    )


def test_payload_returns_a_graph_read_error(tmp_path: Path) -> None:
    assert (
        prefix_stage_riders(
            payload_dir=tmp_path / "payload",
            graph=tmp_path / "missing.fabro",
            stage_riders={"implement": "IMPLEMENT-RIDER\n"},
        )
        is not None
    )


def test_standing_rider_reaches_review_and_proof_stages() -> None:
    sections = stage_rider_sections(
        comments=(
            WorkItemComment(text="STANDING RIDER: STANDING-RIDER", author=None, created_at=None),
        ),
        claim_at=None,
    )

    assert "STANDING-RIDER" in sections["review"]
    assert "STANDING-RIDER" in sections["proof_capture"]
    assert "STANDING-RIDER" in sections["proof_verify"]
