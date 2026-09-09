"""The implement workflow parameterizes its ACP adapters (6pl3in, egms32, tsna).

EVERY ACP node launches its coding-agent adapter via its OWN
`{{ inputs.<node>_adapter }}` rather than a hard-coded command, so the
Dispatcher can route any node to any adapter with
`fabro run --input <node>_adapter=...`. One input per node is what makes
per-node configuration EXPRESSIBLE: the three implementer nodes used to
share a single `acp_adapter`, so `dispatcher.acp_nodes.fix` had nowhere to
land no matter what the configuration said (bd-ib-tsna). Their defaults are
deliberately identical, so the split changed the surface and not the
behaviour.

The PR node stays separate so the publish step -- a fixed `git`/`gh` recipe
with no design judgement in it -- can run on a cheaper tier than the
implementer. The REVIEW node (egms32) is separate so it can run on a
different provider/model (Claude Opus 4.8 + high thinking), and the
DISPOSITION node so adjudication can be pinned independently. All inputs
default in workflow.toml, so the default dispatch behavior is
parameter-driven and never hard-coded.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_WORKFLOW_DOT = _WORKFLOW_DIR / "workflow.fabro"
_WORKFLOW_TOML = _WORKFLOW_DIR / "workflow.toml"
_CLAUDE_ADAPTER = "npx -y @agentclientprotocol/claude-agent-acp"
_CLAUDE_OPUS_5_ADAPTER = (
    "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)
# One adapter input per ACP node, keyed by the node it belongs to.
_NODE_ACP = {
    node: 'acp.command="{{ inputs.' + node + '_adapter }}"'
    for node in ("implement", "fix", "review_fix", "pr", "review", "disposition")
}
_IMPLEMENTER_NODES = ("implement", "fix", "review_fix")


def _acp_lines() -> list[str]:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    return [line.strip() for line in dot.splitlines() if "acp.command=" in line]


def test_every_acp_node_uses_a_parameterized_adapter() -> None:
    """No node hard-codes its adapter; each uses one of the declared inputs."""
    acp_lines = _acp_lines()
    assert acp_lines, "expected at least one acp.command node"
    assert all(line in _NODE_ACP.values() for line in acp_lines)


def test_each_acp_node_has_its_own_adapter_input() -> None:
    """Exactly one node per input, which is what makes per-node config expressible.

    A shared input cannot carry two values, so two nodes on one input means
    configuring either of them alone is unrepresentable — the failure this
    one-to-one mapping exists to remove.
    """
    acp_lines = _acp_lines()
    for node, line in _NODE_ACP.items():
        assert acp_lines.count(line) == 1, node
    assert len(acp_lines) == len(_NODE_ACP)


def test_pr_node_is_the_only_node_on_the_pr_adapter() -> None:
    """The publish node is separated from the implementer tier, and only it.

    The split is what lets the pr node take a cheaper model than
    implement / fix / review_fix — the Claude Haiku default, or a per-repo
    Codex/other override; if another node drifted onto `pr_adapter` it would
    silently inherit that cheaper tier.
    """
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    pr_block = re.search(r"\n    pr \[(.*?)\n    \]", dot, re.DOTALL)
    assert pr_block is not None
    assert _NODE_ACP["pr"] in pr_block.group(1)
    assert _acp_lines().count(_NODE_ACP["pr"]) == 1


def test_no_node_hardcodes_the_claude_adapter_command() -> None:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    assert f'acp.command="{_CLAUDE_ADAPTER}"' not in dot


def test_toml_declares_every_implementer_adapter_defaulting_to_claude_opus_5() -> None:
    """Each implementer node declares its own input, all three on the same default."""
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "[run.inputs]" in toml
    for node in _IMPLEMENTER_NODES:
        assert re.search(
            r"^\s*" + node + r'_adapter\s*=\s*"' + re.escape(_CLAUDE_OPUS_5_ADAPTER) + r'"',
            toml,
            re.MULTILINE,
        ), node


def test_toml_declares_pr_adapter_defaulting_to_claude_haiku() -> None:
    """The publish input pins Claude Haiku 4.5 + high effort via the adapter's
    own env (v107): the pr fleet default is a model-agnostic Claude adapter, so
    a bare `fabro run` and an unconfigured dispatch both render Haiku rather than
    a Codex model. `model`/`reasoning_effort` are API-only attributes fabro
    rejects on acp nodes, so the model rides ANTHROPIC_MODEL on the command."""
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    pr_line = re.search(r'^\s*pr_adapter\s*=\s*"(.+)"', toml, re.MULTILINE)
    assert pr_line is not None
    value = pr_line.group(1)
    assert value == (
        "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high " f"{_CLAUDE_ADAPTER}"
    )


def test_toml_declares_disposition_adapter_defaulting_to_claude() -> None:
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert re.search(
        r'^\s*disposition_adapter\s*=\s*"' + re.escape(_CLAUDE_ADAPTER) + r'"',
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


def test_scenario20_review_has_unconditional_fallback_to_needs_human() -> None:
    """Fabro requires a fallback when a node has conditional custom routing."""
    fallback_edges = _review_edge_lines(to_node="needs_human")
    assert 'review -> needs_human [label="unmatched review outcome"]' in fallback_edges


def test_scenario20_review_fix_cap_counts_fix_rounds_not_review_visits() -> None:
    """Scenario 20: default cap=3 yields exactly three disposition/fix rounds."""
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "review_fix_visit_cap = 4" in toml
    assert "context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}" in dot
    assert re.search(r"disposition \[.*?max_visits=10", dot, re.DOTALL) is not None
    assert re.search(r"review_fix \[.*?max_visits=10", dot, re.DOTALL) is not None
