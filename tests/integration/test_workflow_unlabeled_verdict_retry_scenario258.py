"""Scenario 258 — an unlabeled verdict turn gets one bounded retry.

The workflow itself is the integration seam here: the graph selects the same
ACP stage again, while its command-stage state files distinguish that retry from
a later logical visit.  Reading the committed graph and prompts together keeps
the retry instruction, its bound, and its terminal cause from drifting apart.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_GRAPH = _BUNDLE / "workflow.fabro"


def _dot() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges(*, source: str) -> list[str]:
    return [
        line.strip() for line in _dot().splitlines() if line.strip().startswith(f"{source} -> ")
    ]


def _node_body(*, node: str) -> str:
    matched = re.search(
        rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]",
        _dot(),
        re.DOTALL | re.MULTILINE,
    )
    assert matched is not None, f"workflow declares no {node} node"
    return matched.group("body")


def _prompt(*, name: str) -> str:
    return re.sub(r"\s+", " ", (_BUNDLE / "prompts" / name).read_text(encoding="utf-8"))


def test_scenario_258_retries_an_unlabeled_review_or_replay_once_per_stage_visit() -> None:
    """Scenario 258 — A review or proof_verify turn that succeeds without a verdict label is retried once before it reaches needs_human.

    A reset gateway begins every ordinary stage visit and clears only that
    stage's retry state.  The fallback route then re-enters the same ACP node on
    its first miss; its second miss writes a stage-specific cause for
    ``needs_human``.  Thus a label and a failed turn keep their established
    routing while a later re-entry receives a fresh one-retry allowance.
    """
    graph = parse_workflow_graph(text=_dot())

    assert not isinstance(graph, str), graph
    for stage, entry, retry, prompt in (
        ("review", "review_verdict_entry", "review_verdict_retry", "review.md"),
        (
            "proof_verify",
            "proof_verify_verdict_entry",
            "proof_verify_verdict_retry",
            "proof-verify.md",
        ),
    ):
        entry_body = _node_body(node=entry)
        retry_body = _node_body(node=retry)
        retry_edges = _edges(source=retry)

        assert f"livespec-{stage.replace('_', '-')}-verdict-retry" in entry_body
        assert "rm -f" in entry_body
        assert any(edge.startswith(f"{stage} -> {retry}") for edge in _edges(source=stage))
        assert any(edge.startswith(f"{retry} -> {stage}") for edge in retry_edges)
        assert any(edge.startswith(f"{retry} -> needs_human") for edge in retry_edges)
        assert r"stage: %s\\n" in retry_body
        assert f"{stage}" in retry_body
        assert "recorded no verdict label" in retry_body
        assert "LIVESPEC_VERDICT_RETRY" in retry_body
        assert f"livespec-{stage.replace('_', '-')}-verdict-retry" in _prompt(name=prompt)
        assert "only its verdict" in _prompt(name=prompt)

    assert any(
        edge.startswith("proof_capture -> review_verdict_entry")
        for edge in _edges(source="proof_capture")
    )
    assert any(
        edge.startswith("disposition -> review_verdict_entry")
        for edge in _edges(source="disposition")
    )
    assert "review_verdict_entry -> review" in _edges(source="review_verdict_entry")
    assert any(
        edge.startswith("review -> proof_verify_verdict_entry") for edge in _edges(source="review")
    )
    assert any(
        edge.startswith("proof_grade_route -> proof_verify_verdict_entry")
        for edge in _edges(source="proof_grade_route")
    )
    assert "proof_verify_verdict_entry -> proof_verify" in _edges(
        source="proof_verify_verdict_entry"
    )

    assert 'review -> disposition [label="fix", condition="preferred_label=fix"]' in _edges(
        source="review"
    )
    assert (
        'review -> needs_human [label="Blocked", condition="outcome=failed", weight=100]'
        in _edges(source="review")
    )
    assert (
        'proof_verify -> proof_grade   [label="verified", condition="preferred_label=approve"]'
        in _edges(source="proof_verify")
    )
    assert any(
        edge.startswith("proof_verify -> needs_human")
        and 'condition="outcome=failed"' in edge
        and "weight=100" in edge
        for edge in _edges(source="proof_verify")
    )
