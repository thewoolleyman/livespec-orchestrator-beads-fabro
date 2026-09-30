"""The CLOSED two-form candidate grammar, and the identity the catalogs derive.

Binds two clauses of `SPECIFICATION/contracts.md` that are one mechanism:

- Section "Factory-configurable ACP fallback priority" -> "The candidate grammar
  is closed": "A candidate object is EXACTLY ONE of the two forms ..., and its
  key set is closed to the keys of that form. ... Any other key, and any object
  that carries `agent` together with `command`, `args` or `env`, MUST refuse
  before claim. `config_options` is NOT a configuration key ... and MUST refuse
  if it appears in committed configuration."
- Section "Agent and model catalogs" -> "Resolution and derivation": "Derived
  identity, when not overridden, is: `display_name` = the agent's display name
  followed by the model's display name; `candidate_key` = the canonical
  `<agent>/<provider>/<model>` triple; `availability_key` = the agent entry's
  account domain. ... Built-in identity attaches to a structured candidate by
  catalog resolution, never by byte-equality of the rendered command;
  byte-equality remains the rule for the manual form."

THEY ARE ONE MECHANISM because the discrimination decides BOTH answers. An
object read as structured derives its identity from the catalogs and admits the
structured key set; one read as manual keeps byte-equality and admits the manual
key set. A test that asserted derivation without asserting the discrimination
would pass against an implementation that derived identity for a MIXED object
too -- silently dropping the manual fields the operator wrote.

THE CROSS-NODE CASE IS THE LOAD-BEARING DERIVATION ASSERTION. "Two structured
entries naming the same agent and model therefore share identity across nodes by
construction" is the property the derived triple exists to give, and it is the
one a hand-written identity cannot accidentally satisfy.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_PREFIX = "dispatcher.acp_nodes"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}",
    "fix_adapter": _CLAUDE,
    "review_fix_adapter": _CLAUDE,
    "pr_adapter": _CLAUDE,
    "review_adapter": _CLAUDE,
    "disposition_adapter": _CLAUDE,
}

_OPUS_ENTRY: dict[str, Any] = {
    "agent": "claude-acp",
    "model": "claude-opus-5",
    "effort": "high",
}

_MANUAL_IDENTITY: dict[str, Any] = {
    "display_name": "operator text",
    "candidate_key": "stable-candidate",
    "availability_key": "default-domain",
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _chains(*, block: dict[str, Any]) -> Any:
    """Every node's declared chain metadata for one dispatcher block, or a refusal."""
    catalogs = _module(name="_acp_catalogs").resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    return _module(name="_acp_node_repository").repository_acp_chains(
        block=block, catalogs=catalogs
    )


def _attached(*, block: dict[str, Any]) -> Any:
    """The full resolution: overlays, merge, then chain attachment.

    Both blocks reaching this helper resolve cleanly, so every intermediate
    refusal is asserted away rather than returned: the two cases below are about
    WHICH identity attaches, and returning a refusal here would let either pass
    on a resolution that never happened.
    """
    modules = {
        name: _module(name=name)
        for name in (
            "_acp_catalogs",
            "_acp_node_repository",
            "_acp_node_layers",
            "_acp_builtin_candidates",
            "_acp_chain_resolution",
        )
    }
    catalogs = modules["_acp_catalogs"].resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    overlays = modules["_acp_node_repository"].repository_acp_overlays(
        block=block, catalogs=catalogs
    )
    assert not isinstance(overlays, str), overlays
    declared = modules["_acp_node_repository"].repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolution = modules["_acp_node_layers"].resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )
    assert not isinstance(resolution, str), resolution
    return modules["_acp_chain_resolution"].attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch={},
        builtins=modules["_acp_builtin_candidates"].builtin_acp_identities(
            workflow_inputs=_WORKFLOW_INPUTS, block=block
        ),
    )


def test_the_derivation_and_form_modules_are_committed_files() -> None:
    """Both halves of the one mechanism exist as committed modules."""
    for name in ("_acp_structured_identity", "_acp_candidate_forms"):
        assert (_COMMANDS / f"{name}.py").is_file(), name


def test_a_structured_entry_derives_its_whole_identity_triple() -> None:
    """The three derived fields, exactly as the section spells them out."""
    chains = _chains(block={"acp_nodes": {"implement": _OPUS_ENTRY}})
    assert not isinstance(chains, str), chains
    identity = chains["implement"].identity

    assert identity is not None
    assert identity.display_name == "Claude ACP Claude Opus 5"
    assert identity.candidate_key == "claude-acp/anthropic/claude-opus-5"
    assert identity.availability_key == "anthropic"


def test_a_structured_codex_entry_derives_scenario_129s_candidate_key() -> None:
    """Scenario 129 names the triple literally: `codex-acp/openai/gpt-5.5`."""
    chains = _chains(
        block={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        }
    )
    assert not isinstance(chains, str), chains
    identity = chains["implement"].identity

    assert identity is not None
    assert identity.candidate_key == "codex-acp/openai/gpt-5.5"
    assert identity.availability_key == "codex"


def test_a_multi_provider_reference_derives_the_agent_provider_model_triple() -> None:
    """Scenario 129's second case: identity derives from all three parts."""
    chains = _chains(
        block={"acp_nodes": {"implement": {"agent": "opencode", "model": "zai/glm-5.2"}}}
    )
    assert not isinstance(chains, str), chains
    identity = chains["implement"].identity

    assert identity is not None
    assert identity.candidate_key == "opencode/zai/glm-5.2"
    assert identity.availability_key == "opencode"
    assert identity.display_name == "OpenCode GLM 5.2"


def test_two_nodes_naming_one_agent_and_model_share_identity_by_construction() -> None:
    """The cross-node reuse the derived triple exists to give."""
    chains = _chains(block={"acp_nodes": {"implement": _OPUS_ENTRY, "fix": _OPUS_ENTRY}})
    assert not isinstance(chains, str), chains

    assert chains["implement"].identity == chains["fix"].identity


def test_each_derived_identity_field_is_overridable_on_its_own() -> None:
    """An override wins for the field it names and leaves the others derived."""
    chains = _chains(
        block={
            "acp_nodes": {"implement": {**_OPUS_ENTRY, "availability_key": "chatgpt-team-account"}}
        }
    )
    assert not isinstance(chains, str), chains
    identity = chains["implement"].identity

    assert identity is not None
    assert identity.availability_key == "chatgpt-team-account"
    assert identity.candidate_key == "claude-acp/anthropic/claude-opus-5"
    assert identity.display_name == "Claude ACP Claude Opus 5"


def test_a_structured_entry_is_new_grammar_enabled() -> None:
    """ "New-grammar-enabled" includes "the structured form (`agent`)" by name."""
    chains = _chains(block={"acp_nodes": {"implement": _OPUS_ENTRY}})
    assert not isinstance(chains, str), chains

    assert chains["implement"].enabled is True


def test_an_object_carrying_agent_together_with_a_manual_field_refuses() -> None:
    """The mixed-form refusal, naming the entry and the offending field."""
    for field, value in (("command", "adapter"), ("args", ["-c"]), ("env", {"A": "1"})):
        refusal = _chains(block={"acp_nodes": {"implement": {**_OPUS_ENTRY, field: value}}})
        assert isinstance(refusal, str), field
        assert f"{_PREFIX}.implement" in refusal, (field, refusal)
        assert field in refusal, (field, refusal)
        assert "agent" in refusal, (field, refusal)


def test_a_structured_entry_carrying_an_unknown_key_refuses_naming_it() -> None:
    """The structured key set is closed to its own keys plus the overrides."""
    refusal = _chains(block={"acp_nodes": {"implement": {**_OPUS_ENTRY, "modle": "typo"}}})

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement" in refusal
    assert "'modle'" in refusal


def test_config_options_in_committed_configuration_refuses_in_either_form() -> None:
    """`config_options` is a field of the RENDERED CHAIN, never a configuration key.

    Both forms are checked because the key is refused as CONFIGURATION rather
    than as a violation of one form's key set -- an implementation that only
    closed the structured set would accept it beside a manual `command` and then
    emit an operator-authored chain field to Fabro.
    """
    for entry in (
        {**_OPUS_ENTRY, "config_options": {"model": "claude-opus-5"}},
        {**_MANUAL_IDENTITY, "command": "adapter", "config_options": {"model": "x"}},
    ):
        refusal = _chains(block={"acp_nodes": {"implement": entry}})
        assert isinstance(refusal, str), entry
        assert "config_options" in refusal, (entry, refusal)


def test_a_manual_entry_keeps_byte_equality_and_derives_nothing() -> None:
    """Scenario 129: the manual form is accepted with no field from any catalog."""
    chains = _chains(
        block={
            "acp_nodes": {
                "implement": {
                    **_MANUAL_IDENTITY,
                    "command": "/opt/local/bin/other-acp",
                    "env": {"LOCAL": "1"},
                }
            }
        }
    )
    assert not isinstance(chains, str), chains
    identity = chains["implement"].identity

    assert identity is not None
    assert identity.display_name == "operator text"
    assert identity.candidate_key == "stable-candidate"
    assert identity.availability_key == "default-domain"


def test_a_structured_fallback_entry_derives_its_own_identity() -> None:
    """A fallback in the structured form carries none of the manual fields.

    "A structured-form entry carries none of these and renders them from the
    catalogs" -- so the fallback's complete-`command` requirement, which exists
    only so a manual fallback cannot inherit one, does not apply to it.
    """
    chains = _chains(
        block={
            "acp_nodes": {
                "implement": {
                    **_OPUS_ENTRY,
                    "fallbacks": [
                        {"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"}
                    ],
                }
            }
        }
    )
    assert not isinstance(chains, str), chains
    [fallback] = chains["implement"].fallbacks

    assert fallback.identity is not None
    assert fallback.identity.candidate_key == "claude-acp/anthropic/claude-haiku-4-5"
    assert fallback.adapter.command == _CLAUDE
    assert fallback.adapter.env == {
        "ANTHROPIC_MODEL": "claude-haiku-4-5",
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }


def test_a_structured_fallback_that_cannot_resolve_refuses_naming_its_index() -> None:
    """A fallback's refusal points at the array position an operator has to edit."""
    refusal = _chains(
        block={
            "acp_nodes": {
                "implement": {
                    **_OPUS_ENTRY,
                    "fallbacks": [{"agent": "claude-acp", "model": "claude-opus-99"}],
                }
            }
        }
    )

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0].model" in refusal


def test_a_manual_fallback_still_requires_its_own_complete_command() -> None:
    """The no-inheritance rule for the manual form is untouched by the new form."""
    refusal = _chains(
        block={
            "acp_nodes": {
                "implement": {**_OPUS_ENTRY, "fallbacks": [{**_MANUAL_IDENTITY, "args": ["-x"]}]}
            }
        }
    )

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0].command" in refusal


def test_a_structured_primary_attaches_its_derived_identity_to_the_chain() -> None:
    """Catalog resolution, not byte-equality, is what attaches structured identity.

    The discriminating control is that the rendered bytes of this entry are
    exactly the built-in Anthropic implementer default, which the byte-equality
    table ALSO matches. An implementation preferring the built-in table would
    return the built-in's digest-keyed identity; the derived triple is the
    evidence that catalog resolution won.
    """
    attached = _attached(block={"acp_nodes": {"implement": _OPUS_ENTRY}})
    assert not isinstance(attached, str), attached
    identity = attached.chains["implement"].primary.identity

    assert identity is not None
    assert identity.candidate_key == "claude-acp/anthropic/claude-opus-5"
    assert not identity.candidate_key.startswith("builtin-")


def test_a_manual_primary_matching_a_built_in_still_takes_the_built_in_identity() -> None:
    """Byte-equality remains the rule for the manual form.

    The control for the case above: the SAME rendered bytes, written in the
    manual form, take the byte-keyed built-in identity. Without this leg the
    assertion above is equally consistent with the built-in table having been
    removed altogether.
    """
    attached = _attached(
        block={
            "acp_nodes": {
                "implement": {
                    "command": _CLAUDE,
                    "env": {
                        "ANTHROPIC_MODEL": "claude-opus-5",
                        "CLAUDE_CODE_EFFORT_LEVEL": "high",
                    },
                }
            }
        }
    )
    assert not isinstance(attached, str), attached
    identity = attached.chains["implement"].primary.identity

    assert identity is not None
    assert identity.candidate_key.startswith("builtin-anthropic-")
