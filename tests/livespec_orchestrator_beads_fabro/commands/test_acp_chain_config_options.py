"""Where a candidate's model and effort RIDE, decided by its agent's mechanism.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "In-protocol model and effort selection": "For a candidate whose
agent catalog entry declares the `protocol` mechanism, the rendered chain
candidate MUST carry a `config_options` object mapping ACP session config
option ids to requested values (`model` and, when set, `effort`) ... For a
candidate whose agent entry declares an environment or argument mapping, the
Dispatcher MUST render `model` and `effort` into the adapter exactly as the
mapping states and the handler sets no option; the two mechanisms MUST NOT be
combined for one candidate."

THE PRIMARY IS ASSERTED, NOT ONLY THE FALLBACKS, AND THAT IS THE WHOLE POINT.
A fallback candidate is parsed as a candidate end to end, so it carries
whatever the render produced. The PRIMARY takes a different route: it is
resolved through the three adapter layers as an overlay and the chain's
metadata is attached to it afterwards, so a `config_options` object produced by
the render has to survive that attach or it is silently dropped. Dropping it is
invisible in every other observation -- the adapter bytes are correct, the
identity is correct, the digests are stable -- and the only symptom is an agent
that runs its own default model while the configuration says otherwise.

"MUST NOT BE COMBINED" IS ASSERTED AS AN EXCLUSION IN BOTH DIRECTIONS. A
protocol candidate must put NOTHING in the adapter, and an env or json-env
candidate must put NOTHING on the chain. Asserting only the positive half of
each would pass against a build that emitted both and let the handler and the
adapter race to set the model.

THE AGENTS ARE THE COMMITTED ONES, chosen for their mechanisms rather than
named for their own sake: `glm-acp-agent` declares `protocol`, `claude-acp`
declares the ENV mapping, and `codex-acp` declares the JSON-env mapping. Using
three real catalog entries is what makes this a test of the dispatch rather
than of a fixture.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"

# A deliberately DIFFERENT workflow default per node, so a primary that failed
# to resolve shows up as the placeholder rather than as a coincidence.
_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": "WORKFLOW=implement placeholder-adapter",
    "pr_adapter": "WORKFLOW=pr placeholder-adapter",
    "review_adapter": "WORKFLOW=review placeholder-adapter",
    "disposition_adapter": "WORKFLOW=disposition placeholder-adapter",
}

# `glm-acp-agent` declares the protocol mechanism and, at this registry
# snapshot, NO effort levels -- it is a seeded entry whose levels are not yet
# measured. So the requested options are `model` alone, which is exactly the
# contract's "`model` and, WHEN SET, `effort`".
_PROTOCOL_ENTRY: dict[str, Any] = {"agent": "glm-acp-agent", "model": "glm-5.2"}
_ENV_ENTRY: dict[str, Any] = {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}
_JSON_ENV_ENTRY: dict[str, Any] = {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _chain(*, entry: dict[str, Any], node: str = "implement") -> Any:
    """One node's RESOLVED chain, through the real three-layer path.

    Every earlier stage is asserted rather than returned: a refusal from the
    wrong stage reads exactly like the answer these cases mean to assert.
    """
    block = {"acp_nodes": {node: entry}}
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()
    repository = _module(name="_acp_node_repository")
    overlays = repository.repository_acp_overlays(block=block, catalogs=catalogs)
    assert not isinstance(overlays, str), overlays
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolution = _module(name="_acp_node_layers").resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )
    assert not isinstance(resolution, str), resolution
    attached = _module(name="_acp_chain_resolution").attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch={},
        builtins=_module(name="_acp_builtin_candidates").builtin_acp_identities(
            workflow_inputs=_WORKFLOW_INPUTS
        ),
    )
    assert not isinstance(attached, str), attached
    return attached.chains[node]


def test_a_protocol_agents_primary_carries_its_requested_options_on_the_chain() -> None:
    """The requested options survive the attach onto the resolved primary."""
    primary = _chain(entry=dict(_PROTOCOL_ENTRY)).primary

    assert dict(primary.config_options) == {"model": "glm-5.2"}


def test_a_protocol_agents_primary_puts_nothing_in_its_adapter() -> None:
    """Half of "MUST NOT be combined": the adapter carries no model at all."""
    primary = _chain(entry=dict(_PROTOCOL_ENTRY)).primary
    rendered = _module(name="_acp_node_adapters").render_adapter(adapter=primary.adapter)

    assert dict(primary.adapter.env) == {}
    assert primary.adapter.args == ()
    assert "glm-5.2" not in rendered


def test_an_env_mechanism_primary_renders_into_the_adapter_and_carries_no_options() -> None:
    """The other half: an env mapping puts the pin in the adapter, nowhere else."""
    primary = _chain(entry=dict(_ENV_ENTRY)).primary
    rendered = _module(name="_acp_node_adapters").render_adapter(adapter=primary.adapter)

    assert dict(primary.config_options) == {}
    assert rendered == f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"


def test_a_json_env_mechanism_primary_renders_into_the_adapter_and_carries_no_options() -> None:
    """A JSON-env mapping is an adapter mapping too, not a protocol one."""
    primary = _chain(entry=dict(_JSON_ENV_ENTRY)).primary

    assert dict(primary.config_options) == {}
    assert '"model":"gpt-5.5"' in primary.adapter.env["CODEX_CONFIG"]


def test_a_protocol_agents_fallback_carries_its_options_too() -> None:
    """ "Primary or fallback": the chain's later candidates answer the same rule."""
    chain = _chain(entry={**_ENV_ENTRY, "fallbacks": [dict(_PROTOCOL_ENTRY)]})
    [fallback] = chain.fallbacks

    assert dict(fallback.config_options) == {"model": "glm-5.2"}
    assert dict(chain.primary.config_options) == {}
