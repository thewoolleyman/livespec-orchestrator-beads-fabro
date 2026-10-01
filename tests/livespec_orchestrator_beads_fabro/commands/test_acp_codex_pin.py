"""Every Codex candidate is pinned, and the ONE opt-out is the manual form.

Binds `SPECIFICATION/contracts.md` section "Built-in ACP node defaults":
"A candidate whose `agent` is `codex-acp`, primary or fallback, MUST carry both
`model` and `effort`, and the Dispatcher MUST refuse before claim one that does
not. ... The one deliberate exception is the explicit un-pinned opt-out: a
MANUAL-form candidate whose `command` is the baked path below and whose
`CODEX_CONFIG` carries no `model` key. It MUST render byte-identically to the
un-pinned base string spelled out below. There is no structured spelling of the
opt-out, so an operator who disables the pin does so visibly, in the
escape-hatch form."

WHY THE RULE IS AGENT-SPECIFIC RATHER THAN GENERAL, which is what the
`claude-acp` control below protects. An entry declaring no `effort` is
ORDINARILY admissible -- it is the candidate taking the adapter's own default,
and every agent has one. For `codex-acp` it is not, and the contract gives a
mechanical reason rather than a stylistic one: the sandbox image bakes a
`codex-acp` build whose models-manager cannot decode the current catalog, so an
unpinned adapter falls back to a baked static list and its effective model is
the residue of a decode failure. A test that asserted the refusal without the
`claude-acp` control would pass just as well against a build that had made
`effort` mandatory for EVERY agent -- which would break the un-pinned Claude
disposition default this repository ships.

"PRIMARY OR FALLBACK" IS ASSERTED IN BOTH POSITIONS. The two reach the renderer
by different routes -- a node entry through `_acp_node_repository`, a fallback
through `_acp_node_chains._one_fallback` -- so one passing is not evidence about
the other.

THE OPT-OUT IS ASSERTED AS A CANDIDATE, WHICH IS THE CONTRACT'S OWN WORD. A
candidate carries its whole adapter and resolves through no layer merge, so the
bytes asserted here are the bytes a chain would execute. The byte target is the
ratified literal written out rather than imported: a test reading the renderer's
own constant could not tell a deliberate change from a regression.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CODEX_PATH = "/opt/livespec/codex-acp/bin/codex-acp"
_UNPINNED_CODEX_CONFIG = '{"approval_policy":"never","sandbox_mode":"danger-full-access"}'
_UNPINNED_BASE = (
    f"CODEX_CONFIG='{_UNPINNED_CODEX_CONFIG}' "
    f"INITIAL_AGENT_MODE=agent-full-access {_CODEX_PATH}"
)


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _catalogs() -> Any:
    return _module(name="_acp_catalogs").builtin_catalogs()


def _node_entry(*, entry: dict[str, Any], node: str = "implement") -> Any:
    """One node entry resolved through the repository layer, or its refusal."""
    return _module(name="_acp_node_repository").repository_acp_overlays(
        block={"acp_nodes": {node: entry}}, catalogs=_catalogs()
    )


def _chain(*, entry: dict[str, Any], node: str = "implement") -> Any:
    """One node's chain, which is where a FALLBACK candidate is parsed."""
    return _module(name="_acp_node_repository").repository_acp_chains(
        block={"acp_nodes": {node: entry}}, catalogs=_catalogs()
    )


def test_a_structured_codex_primary_without_effort_refuses_before_claim() -> None:
    """A pinned model with no effort is still an unpinned adapter."""
    refusal = _node_entry(entry={"agent": "codex-acp", "model": "gpt-5.5"})

    assert isinstance(
        refusal, str
    ), f"a codex-acp entry with no effort must refuse before claim; got {refusal!r}"
    assert "dispatcher.acp_nodes.implement" in refusal
    assert "effort" in refusal


def test_a_structured_codex_primary_without_model_refuses_before_claim() -> None:
    """The other half of "both `model` and `effort`"."""
    refusal = _node_entry(entry={"agent": "codex-acp", "effort": "high"})

    assert isinstance(refusal, str), refusal
    assert "dispatcher.acp_nodes.implement" in refusal
    assert "model" in refusal


def test_a_structured_codex_fallback_without_effort_refuses_before_claim() -> None:
    """ "Primary or fallback": the fallback array answers to the same rule."""
    refusal = _chain(
        entry={
            "agent": "codex-acp",
            "model": "gpt-5.5",
            "effort": "high",
            "fallbacks": [{"agent": "codex-acp", "model": "gpt-5.4"}],
        }
    )

    assert isinstance(
        refusal, str
    ), f"a codex-acp FALLBACK with no effort must refuse before claim; got {refusal!r}"
    assert "fallbacks[0]" in refusal
    assert "effort" in refusal


def test_a_fully_pinned_structured_codex_candidate_resolves() -> None:
    """The control: the refusal is about the missing pin, not about codex-acp."""
    overlays = _node_entry(entry={"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"})

    assert not isinstance(overlays, str), overlays
    assert overlays["implement"].command == _CODEX_PATH


def test_another_agent_without_effort_still_resolves() -> None:
    """The rule is `codex-acp`'s, not a new requirement on every agent.

    Without this control the refusal above is equally consistent with a build
    that made `effort` mandatory everywhere -- which would refuse the un-pinned
    Claude disposition default this repository ships.
    """
    overlays = _node_entry(entry={"agent": "claude-acp", "model": "claude-opus-5"})

    assert not isinstance(overlays, str), overlays
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in overlays["implement"].env


def test_the_manual_form_opt_out_candidate_renders_the_un_pinned_base_string() -> None:
    """The one deliberate exception, rendered byte for byte.

    A CANDIDATE carries its whole adapter and merges with no layer, so these
    are the bytes a chain would execute. The posture keys are present and the
    `model` / `model_reasoning_effort` keys are absent -- the opt-out is the
    absence of a pin, never a pin spelled with empty values.
    """
    chain = _chain(
        entry={
            "agent": "codex-acp",
            "model": "gpt-5.5",
            "effort": "high",
            "fallbacks": [
                {
                    "command": _CODEX_PATH,
                    "env": {
                        "CODEX_CONFIG": _UNPINNED_CODEX_CONFIG,
                        "INITIAL_AGENT_MODE": "agent-full-access",
                    },
                    "display_name": "un-pinned Codex",
                    "candidate_key": "codex-unpinned",
                    "availability_key": "codex",
                }
            ],
        }
    )

    assert not isinstance(chain, str), chain
    [opt_out] = chain["implement"].fallbacks
    rendered = _module(name="_acp_node_adapters").render_adapter(adapter=opt_out.adapter)

    assert rendered == _UNPINNED_BASE
    assert '"model"' not in rendered
    assert '"model_reasoning_effort"' not in rendered
