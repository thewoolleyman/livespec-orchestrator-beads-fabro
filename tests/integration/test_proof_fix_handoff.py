"""Pin the workflow half of the proof-to-fix transport (bd-ib-yastku).

Fabro's compact preamble excludes agent response text. summary:high includes
the source-labelled response, even when its outcome is succeeded. These tests
assert the actual graph selection, not a Python imitation of Fabro's renderer.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")


@pytest.mark.parametrize("source", ["proof_capture", "proof_verify", "janitor"])
def test_every_fix_entry_preserves_source_response(source: str) -> None:
    text = (_BUNDLE / "workflow.fabro").read_text()
    graph = parse_workflow_graph(text=text)
    assert "fix" in graph.successors(node=source)
    fix = next(node for node in graph.nodes if node.name == "fix")
    assert fix.attributes.get("fidelity") == "summary:high"
    # Incoming edges override node fidelity in Fabro; none may silently restore
    # compact mode and strip proof findings from this node's preamble.
    edges = [line for line in text.splitlines() if line.strip().startswith(f"{source} -> fix")]
    assert edges
    assert all("fidelity=" not in edge or 'fidelity="summary:high"' in edge for edge in edges)


def test_fix_prompt_consumes_semantic_findings_and_fails_closed() -> None:
    prompt = " ".join((_BUNDLE / "prompts/fix.md").read_text().split())
    assert "proof_capture" in prompt
    assert "proof_verify" in prompt
    assert "most recent incoming stage" in prompt
    assert "green janitor does not discharge" in prompt
    assert "missing or unreadable" in prompt
    assert '"outcome": "failed"' in prompt
    assert "janitor failure output" in prompt
    assert "reproduction" in prompt


def test_proof_prompts_remain_read_only_and_route_findings_to_fix() -> None:
    for name in ("proof-capture.md", "proof-verify.md"):
        prompt = (_BUNDLE / "prompts" / name).read_text()
        assert "MUST NOT modify the tree" in prompt
        assert '{"preferred_next_label": "fix"}' in prompt
