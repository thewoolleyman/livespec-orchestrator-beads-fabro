"""The implement workflow parameterizes its ACP adapters (work-items 6pl3in, egms32).

The IMPLEMENTER nodes (implement, fix, pr, review_fix) launch their coding-agent
adapter via `{{ inputs.acp_adapter }}` rather than a hard-coded command, so the
Dispatcher can route the implementer work to a Codex worker with
`fabro run --input acp_adapter=...`. The REVIEW node (egms32) launches via a
SEPARATE `{{ inputs.review_adapter }}` so it can run on a different
provider/model (Claude Opus 4.8 + high thinking) from the implementers. Both
inputs default in workflow.toml so the default dispatch behavior is
parameter-driven, never hard-coded.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_WORKFLOW_DOT = _WORKFLOW_DIR / "workflow.fabro"
_WORKFLOW_TOML = _WORKFLOW_DIR / "workflow.toml"
_CLAUDE_ADAPTER = "npx -y @agentclientprotocol/claude-agent-acp"
_IMPLEMENTER_ACP = 'acp.command="{{ inputs.acp_adapter }}"'
_REVIEW_ACP = 'acp.command="{{ inputs.review_adapter }}"'
_EXPECTED_IMPLEMENTER_ACP_LINES = 4  # implement, fix, pr, review_fix
_EXPECTED_REVIEW_ACP_LINES = 1  # review


def _acp_lines() -> list[str]:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    return [line.strip() for line in dot.splitlines() if "acp.command=" in line]


def test_every_acp_node_uses_a_parameterized_adapter() -> None:
    """No node hard-codes its adapter; each uses acp_adapter or review_adapter."""
    acp_lines = _acp_lines()
    assert acp_lines, "expected at least one acp.command node"
    assert all(line in (_IMPLEMENTER_ACP, _REVIEW_ACP) for line in acp_lines)


def test_implementer_and_review_nodes_use_their_respective_inputs() -> None:
    acp_lines = _acp_lines()
    assert acp_lines.count(_IMPLEMENTER_ACP) == _EXPECTED_IMPLEMENTER_ACP_LINES
    assert acp_lines.count(_REVIEW_ACP) == _EXPECTED_REVIEW_ACP_LINES


def test_no_node_hardcodes_the_claude_adapter_command() -> None:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    assert f'acp.command="{_CLAUDE_ADAPTER}"' not in dot


def test_toml_declares_acp_adapter_defaulting_to_claude() -> None:
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "[run.inputs]" in toml
    assert re.search(
        r'^\s*acp_adapter\s*=\s*"' + re.escape(_CLAUDE_ADAPTER) + r'"',
        toml,
        re.MULTILINE,
    )


def test_toml_declares_review_adapter_pinned_to_opus_high_thinking() -> None:
    """The review input pins Opus 4.8 + high effort via the adapter's own env.

    `model`/`reasoning_effort` are API-only attributes fabro rejects on acp
    nodes, so the model is pinned through the Claude Code adapter's own env
    (ANTHROPIC_MODEL + CLAUDE_CODE_EFFORT_LEVEL), prefixed onto the command.
    """
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    review_line = re.search(r'^\s*review_adapter\s*=\s*"(.+)"', toml, re.MULTILINE)
    assert review_line is not None
    value = review_line.group(1)
    assert "ANTHROPIC_MODEL=claude-opus-4-8" in value
    assert "CLAUDE_CODE_EFFORT_LEVEL=high" in value


def _review_edge_lines(*, to_node: str) -> list[str]:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    return [
        line.strip() for line in dot.splitlines() if line.strip().startswith(f"review -> {to_node}")
    ]


def test_scenario20_review_approve_edge_is_conditioned() -> None:
    """Scenario 20: approve reaches PR only through an explicit condition."""
    pr_edges = _review_edge_lines(to_node="pr")
    approve_edges = [line for line in pr_edges if 'label="approve"' in line]
    assert approve_edges == [
        'review -> pr         [label="approve", condition="preferred_label=approve"]'
    ]
    assert all("condition=" in line for line in pr_edges)


def test_scenario20_review_cap_routes_to_escape_hatch_or_needs_human() -> None:
    """Scenario 20: a still-blocking capped review ships only via the escape hatch."""
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    assert (
        'condition="preferred_label=fix && context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}"'
        in dot
    )
    assert 'label="ship on review cap"' in dot
    assert "outcome={{ inputs.merge_on_review_cap_outcome }}" in dot
    assert 'label="needs-human"' in dot
    assert "outcome!={{ inputs.merge_on_review_cap_outcome }}" in dot
    assert "advisory" not in dot
    assert "SHIP-ON-CAP" not in dot


def test_scenario20_review_has_unconditional_fallback_to_human_gate() -> None:
    """Fabro requires a fallback when a node has conditional custom routing."""
    escalate_edges = _review_edge_lines(to_node="escalate")
    assert 'review -> escalate   [label="unmatched review outcome"]' in escalate_edges


def test_scenario20_review_fix_cap_counts_fix_rounds_not_review_visits() -> None:
    """Scenario 20: default cap=3 yields exactly three review-fix rounds."""
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "review_fix_visit_cap = 4" in toml
    assert "context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}" in dot
    assert re.search(r"review_fix \[.*?max_visits=4", dot, re.DOTALL) is not None
