"""Rendering a STRUCTURED candidate into the manual form, before anything else.

Binds `SPECIFICATION/contracts.md` section "ACP node adapter configuration":
"The Dispatcher MUST render a structured entry into the manual form below before
any layer merge, journal, digest or run input, so every downstream rule of this
section and of §-Factory-configurable ACP fallback priority applies to the
rendered candidate unchanged. Rendering MUST be deterministic: the same catalog
snapshot and the same entry MUST render byte-identical adapter bytes."

"BEFORE ANY LAYER MERGE" IS ASSERTED THROUGH THE MERGE, not against the renderer
alone. A unit assertion that `render_structured_adapter` returns the right triple
would pass just as well against a Dispatcher that rendered afterwards and threw
the result away; the discriminating evidence is that a structured
`dispatcher.acp_nodes` entry reaches `resolve_acp_nodes` as an ordinary
manual-form overlay and comes out of the three-layer merge as the rendered bytes.
So each case resolves the real repository layer and reads the answer off the
resolution.

THE BYTE TARGETS ARE THE RATIFIED LITERALS, RESTATED. Sections "Built-in ACP node
defaults" and "ACP node adapter configuration" spell out the v107 Claude strings
and the Codex base string exactly, and a reader must be able to predict them from
the specification alone. A test importing the catalog's own constants could not
tell a deliberate change from a regression, so the strings are written out here
and the renderer has to meet them.

DETERMINISM IS ASSERTED ACROSS TWO INDEPENDENT RESOLUTIONS rather than two calls
to one function. Two calls prove the function is not stateful; two resolutions
prove the whole path -- catalog resolution, render, parse, merge, re-render -- is,
which is the claim the contract actually makes about a dispatch.
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_CLAUDE_OPUS_5 = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
_CLAUDE_HAIKU = f"ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
_CODEX_PATH = "/opt/livespec/codex-acp/bin/codex-acp"
_CODEX_PINNED = (
    'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.5",'
    '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
    f"INITIAL_AGENT_MODE=agent-full-access {_CODEX_PATH}"
)

# A deliberately DIFFERENT workflow default per node, so a rendered structured
# entry that failed to replace it would show up as the wrong string rather than
# as a coincidence.
_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": "WORKFLOW=implement placeholder-adapter",
    "fix_adapter": "WORKFLOW=fix placeholder-adapter",
    "review_fix_adapter": "WORKFLOW=review_fix placeholder-adapter",
    "pr_adapter": "WORKFLOW=pr placeholder-adapter",
    "review_adapter": "WORKFLOW=review placeholder-adapter",
    "disposition_adapter": "WORKFLOW=disposition placeholder-adapter",
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _resolved(*, block: dict[str, Any]) -> Any:
    """Every node's resolved adapter for one dispatcher block, or the refusal.

    The whole real path: catalogs resolved from the block, the repository layer
    resolved against them, then the three-layer merge. Every block here declares
    a well-formed catalog, so a catalog refusal is asserted away rather than
    returned -- a catalog fault is a DIFFERENT claim, and returning it here would
    give every refusal case below a second, silent way to pass.
    """
    catalogs = _module(name="_acp_catalogs").resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    overlays = _module(name="_acp_node_repository").repository_acp_overlays(
        block=block, catalogs=catalogs
    )
    if isinstance(overlays, str):
        return overlays
    return _module(name="_acp_node_layers").resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )


def _rendered(*, block: dict[str, Any]) -> dict[str, str]:
    resolution = _resolved(block=block)
    assert not isinstance(resolution, str), resolution
    return {node: node_resolution.rendered for node, node_resolution in resolution.nodes.items()}


def test_the_structured_render_module_is_a_committed_file() -> None:
    """The structured-form renderer exists as a committed module."""
    path = (
        _REPO_ROOT
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_acp_structured_render.py"
    )
    assert path.is_file()


def test_a_structured_claude_entry_renders_the_ratified_v107_bytes() -> None:
    """`{agent, model, effort}` renders the Claude env assignments exactly."""
    rendered = _rendered(
        block={
            "acp_nodes": {
                "implement": {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"},
                "pr": {"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"},
            }
        }
    )

    assert rendered["implement"] == _CLAUDE_OPUS_5
    assert rendered["pr"] == _CLAUDE_HAIKU
    assert "WORKFLOW=" not in rendered["implement"]


def test_a_structured_codex_entry_renders_the_pinned_base_string() -> None:
    """A pinned Codex entry is the base string with the two keys added inside."""
    rendered = _rendered(
        block={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        }
    )

    assert rendered["implement"] == _CODEX_PINNED
    assert rendered["implement"].endswith(f" {_CODEX_PATH}")
    assert " -c model=" not in rendered["implement"]
    tokenized = shlex.split(rendered["implement"])[0].removeprefix("CODEX_CONFIG=")
    assert json.loads(tokenized) == {
        "approval_policy": "never",
        "model": "gpt-5.5",
        "model_reasoning_effort": "high",
        "sandbox_mode": "danger-full-access",
    }


def test_a_structured_entry_leaves_every_node_it_does_not_name_alone() -> None:
    """One node's entry changes one node."""
    rendered = _rendered(
        block={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        }
    )

    assert rendered["pr"] == "WORKFLOW=pr placeholder-adapter"
    assert rendered["review"] == "WORKFLOW=review placeholder-adapter"


def test_a_structured_entry_replaces_the_workflow_default_environment() -> None:
    """A rendered structured entry is a COMPLETE adapter, so it takes the whole env.

    Merging would prefix the workflow default's own model pin onto an adapter
    that is not its provider's -- the identical defect the retired `codex_models`
    expansion set `env_replaces` for.
    """
    rendered = _rendered(
        block={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        }
    )
    assert "WORKFLOW=implement" not in rendered["implement"]


def test_a_node_that_performs_no_writes_renders_the_read_only_posture() -> None:
    """Scenario 90: a review node routed to Codex is rendered `read-only`."""
    rendered = _rendered(
        block={
            "acp_nodes": {
                "review": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"},
                "implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"},
            }
        }
    )

    assert "INITIAL_AGENT_MODE=read-only" in rendered["review"]
    assert "INITIAL_AGENT_MODE=agent-full-access" not in rendered["review"]
    assert "INITIAL_AGENT_MODE=agent-full-access" in rendered["implement"]


def test_a_structured_entry_without_effort_renders_only_the_model() -> None:
    """`effort` is optional, and omitting it omits the key rather than emptying it."""
    rendered = _rendered(
        block={"acp_nodes": {"implement": {"agent": "claude-acp", "model": "claude-opus-5"}}}
    )

    assert rendered["implement"] == f"ANTHROPIC_MODEL=claude-opus-5 {_CLAUDE}"
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in rendered["implement"]


def test_a_structured_entry_resolves_a_model_by_one_of_its_declared_aliases() -> None:
    """An alias resolves to the canonical id, and the canonical id is what renders."""
    rendered = _rendered(
        block={
            "model_catalog": {
                "anthropic/claude-opus-5": {
                    "display_name": "Claude Opus 5",
                    "canonical_id": "claude-opus-5-20260930",
                    "aliases": ["opus"],
                }
            },
            "acp_nodes": {"implement": {"agent": "claude-acp", "model": "opus", "effort": "high"}},
        }
    )
    assert rendered["implement"] == (
        f"ANTHROPIC_MODEL=claude-opus-5-20260930 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
    )


def test_a_multi_provider_agent_takes_a_provider_qualified_model() -> None:
    """Scenario 129: `zai/glm-5.2` resolves for the multi-provider `opencode`."""
    block: dict[str, Any] = {
        "acp_nodes": {"implement": {"agent": "opencode", "model": "zai/glm-5.2"}}
    }
    rendered = _rendered(block=block)

    # The registry declares a per-platform `binary` distribution for `opencode`,
    # so its launch triple is the archive's own `cmd` plus `args`.
    assert rendered["implement"] == "./opencode acp"


def test_a_single_provider_agent_accepts_its_own_provider_qualified_reference() -> None:
    """A qualified reference naming the agent's own provider resolves identically."""
    qualified = _rendered(
        block={
            "acp_nodes": {
                "implement": {
                    "agent": "claude-acp",
                    "model": "anthropic/claude-opus-5",
                    "effort": "high",
                }
            }
        }
    )
    assert qualified["implement"] == _CLAUDE_OPUS_5


def test_a_provider_qualified_reference_naming_another_provider_refuses() -> None:
    """A single-provider agent cannot be pointed at a provider it does not serve."""
    refusal = _resolved(
        block={"acp_nodes": {"implement": {"agent": "claude-acp", "model": "openai/gpt-5.5"}}}
    )

    assert isinstance(refusal, str)
    assert "dispatcher.acp_nodes.implement" in refusal
    assert "openai" in refusal


def test_a_bare_model_on_a_multi_provider_agent_refuses() -> None:
    """A multi-provider agent has no default provider to resolve a bare id against."""
    refusal = _resolved(
        block={"acp_nodes": {"implement": {"agent": "opencode", "model": "glm-5.2"}}}
    )

    assert isinstance(refusal, str)
    assert "dispatcher.acp_nodes.implement.model" in refusal
    assert "provider" in refusal


def test_rendering_is_byte_identical_across_two_independent_resolutions() -> None:
    """The determinism clause, across the whole resolution path rather than one call."""
    block: dict[str, Any] = {
        "acp_nodes": {
            "implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"},
            "pr": {"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"},
        }
    }
    assert _rendered(block=block) == _rendered(block=dict(block))


def test_a_manual_form_entry_still_resolves_beside_a_structured_one() -> None:
    """The escape hatch stays accepted everywhere the structured form is."""
    rendered = _rendered(
        block={
            "acp_nodes": {
                "implement": {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"},
                "review": {"command": "/opt/local/bin/other-acp", "env": {"LOCAL": "1"}},
            }
        }
    )

    assert rendered["implement"] == _CLAUDE_OPUS_5
    assert rendered["review"] == "LOCAL=1 WORKFLOW=review /opt/local/bin/other-acp"
