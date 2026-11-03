"""Scenario 235 — a malformed captured comment is re-captured, not fixed.

The review prompt is the operative implementation of the finding: it must make
the reviewer name the malformed captured comment and its empty run identifier,
classify the defect as proof-record-only, and emit the recapture label.  The
committed graph then proves that label reaches the bounded recapture route
without spending either review-fix stage.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"
_REVIEW_PROMPT = _PAYLOAD / "prompts" / "review.md"


def _collapsed_prompt() -> str:
    return re.sub(r"\s+", " ", _REVIEW_PROMPT.read_text(encoding="utf-8"))


def _edges() -> set[tuple[str, str, str]]:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return {
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in graph.edges
    }


def test_a_non_record_capture_is_a_proof_record_recapture_verdict() -> None:
    """The empty run id is named, then routes directly through the two-lap path."""
    prompt = _collapsed_prompt()

    assert "newest captured Proof of Done comment does not parse as a record" in prompt
    assert "header carries an empty run id" in prompt
    assert "Name the comment and state that its header carries no run id" in prompt
    assert "Exactly these five are proof-record findings" in prompt
    assert "A newest captured Proof of Done comment that does not parse as a record" in prompt
    assert '"preferred_next_label": "recapture"' in prompt

    edges = _edges()
    assert ("review", "recapture_route", "preferred_label=recapture") in edges
    assert ("recapture_route", "proof_capture", "") in edges
    assert ("review", "disposition", "preferred_label=recapture") not in edges
    assert ("review", "review_fix", "preferred_label=recapture") not in edges
