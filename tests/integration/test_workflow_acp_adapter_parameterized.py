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
DISPOSITION node so adjudication can be pinned independently, and the
DOD_GATE node so grading a Definition of Done takes the review tier rather
than inheriting whatever tier a target moved for implementation. All inputs
default in workflow.toml, so the default dispatch behavior is
parameter-driven and never hard-coded.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import builtin_catalogs
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import workflow_layer

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
    for node in (
        "dod_gate",
        "implement",
        "fix",
        "review_fix",
        "proof_capture",
        "proof_verify",
        "pr",
        "review",
        "disposition",
    )
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


def _rendered_defaults() -> dict[str, str]:
    """The committed adapter inputs as a dispatch resolves them.

    Read through `workflow_layer` rather than scanned out of the text: the
    built-in defaults are STRUCTURED entries since contracts.md section
    "Built-in ACP node defaults" moved them off class-shaped strings, so the
    declared value is a catalog reference and the adapter bytes are what the
    render produces. A regex over the raw TOML would grade the reference.
    """
    rendered = workflow_layer(committed=_WORKFLOW_TOML, catalogs=builtin_catalogs())
    assert not isinstance(rendered, str), rendered
    return dict(rendered)


def test_toml_declares_every_implementer_adapter_defaulting_to_claude_opus_5() -> None:
    """Each implementer node declares its own input, all three on the same default."""
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "[run.inputs]" in toml
    rendered = _rendered_defaults()

    for node in _IMPLEMENTER_NODES:
        assert rendered[f"{node}_adapter"] == _CLAUDE_OPUS_5_ADAPTER, node


def test_toml_declares_pr_adapter_defaulting_to_claude_haiku() -> None:
    """The publish input pins Claude Haiku 4.5 + high effort via the adapter's
    own env (v107): the pr fleet default is a model-agnostic Claude adapter, so
    a bare `fabro run` and an unconfigured dispatch both render Haiku rather than
    a Codex model. `model`/`reasoning_effort` are API-only attributes fabro
    rejects on acp nodes, so the model rides ANTHROPIC_MODEL on the command."""
    assert _rendered_defaults()["pr_adapter"] == (
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
    """Scenario 20: approve leaves review only through an explicit condition.

    S6 / bd-ib-msnlnv retargeted this edge from `pr` to `proof_verify`, so what
    approve now reaches is the replay and not publication. The CONDITION is what
    Scenario 20 is about and it is unchanged; the target moved because the
    contract forbids any route to `pr` that has not replayed the proof.
    """
    verify_edges = _review_edge_lines(to_node="proof_verify")
    approve_edges = [line for line in verify_edges if 'label="approve"' in line]
    assert approve_edges == [
        'review -> proof_verify [label="approve", condition="preferred_label=approve"]'
    ]
    assert all("condition=" in line for line in verify_edges)
    # The retarget is total: nothing leaves review for `pr` any more. Tokenized
    # rather than prefix-matched, because `pr` is a prefix of `proof_verify` and a
    # prefix test could never return the other answer.
    assert not [
        line
        for line in _review_edge_lines(to_node="pr")
        if line.split("->", 1)[1].strip().split(maxsplit=1)[0] == "pr"
    ]


def _code_text(*, text: str) -> str:
    """The graph with its `//` comment lines dropped.

    An absence assertion over the raw text cannot distinguish a token the graph
    DECLARES from one its comments merely NAME while recording why it was
    removed — and this graph's comments name every removed token deliberately.
    """
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def test_scenario20_review_routes_on_the_label_alone_with_no_cap_edges() -> None:
    """Scenario 20: the three cap edges are gone; the review loop routes on the label.

    Plan `fabro-currency` P4 (bd-ib-hti4zf) removed all three. Each read an
    `inputs.*` token inside an edge condition, which the Petri-era engine rejects
    AT LOAD with `attractor.condition.syntax` — those three errors are the entire
    reason the candidate refused this graph in the 2026-10-08 Enemy Unit Test
    comparison — and each also read `context.internal.node_visit_count`, which
    that engine does not populate even when the cap is rendered to a literal.

    WHAT THAT COSTS, pinned here rather than left to drift: `merge_on_review_cap
    = true` has no graph expression any more, so the escape hatch cannot ship an
    exhausted review budget. The `false` posture — do not ship, escalate to
    blocked / needs-human — is what a `review_fix.max_visits` run failure
    produces, so the DEFAULT survives and only the hatch is lost. Re-expressing
    it needs an engine that evaluates a counter in a condition, or a contract
    amendment; both are maintainer-owned.
    """
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    # Comment lines are stripped before the absence assertions: the graph's own
    # comments NAME the removed tokens in order to record why they went, and a
    # raw-text scan would read that record as the defect it documents.
    code = _code_text(text=dot)
    assert 'review -> disposition [label="fix", condition="preferred_label=fix"]' in code
    assert 'label="ship on review cap"' not in code
    assert "inputs.merge_on_review_cap_outcome" not in code
    assert "inputs.review_fix_visit_cap" not in code
    assert "context.internal.node_visit_count" not in code
    assert "advisory" not in dot
    assert "SHIP-ON-CAP" not in dot


def test_scenario20_review_has_unconditional_fallback_to_needs_human() -> None:
    """Fabro requires a fallback when a node has conditional custom routing."""
    fallback_edges = _review_edge_lines(to_node="needs_human")
    assert 'review -> needs_human [label="unmatched review outcome"]' in fallback_edges


def test_scenario20_the_review_fix_loop_is_bounded_on_its_own_nodes() -> None:
    """Scenario 20: the loop's bound is `max_visits` on the two nodes it drives.

    `review_fix_visit_cap` is still DECLARED in the run config — the Dispatcher
    renders it, and removing the input is a separate, maintainer-owned decision —
    but since plan `fabro-currency` P4 no edge condition reads it, so it no
    longer moves the bound. What does is the `max_visits` on `disposition` and
    `review_fix`, asserted here, and exhausting it fails the run rather than
    routing to a cap disposition.
    """
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "review_fix_visit_cap = 4" in toml
    assert "inputs.review_fix_visit_cap" not in _code_text(text=dot)
    # THREE, which is what the retired `review_fix_visit_cap` guard admitted at
    # the default cap of three fix rounds. The number is load-bearing: the
    # execution-budget derivation reads it as the loop's bound now that the guard
    # is gone, and the credential gate sizes a required credential lifetime from
    # the result, so the retired backstop value of 10 would have raised the
    # derived allowance past anything a real credential carries.
    assert re.search(r"disposition \[.*?max_visits=3\n", dot, re.DOTALL) is not None
    assert re.search(r"review_fix \[.*?max_visits=3\n", dot, re.DOTALL) is not None
