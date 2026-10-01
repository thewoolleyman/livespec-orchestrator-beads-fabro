"""The factory-capability gate on a chain carrying ACP new grammar.

`SPECIFICATION/scenarios.md` Scenario 127, "New grammar is version-gated
against the resolved factory": "Given a node carries identity, signature,
pricing, or a non-empty fallback field / When dispatcher.minimum_release is
below the first supporting release or the resolved factory server lacks the
pinned Fabro capability / Then dispatch refuses before claim or run creation /
And a local Fabro binary is not evidence of the remote capability." This module
owns the FACTORY half of that gate; the release half is the committed floor
`_dispatcher_minimum_release_floor` reads.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "In-protocol model and effort selection" adds the narrower second
arm: "The Fabro server MUST advertise the additive capability
`acp.candidate_config_options.v1` alongside `acp.fallback_chain.v1`, and the
Dispatcher MUST refuse before claim a chain carrying `config_options` when the
resolved factory server does not advertise it, exactly as the existing
capability gate does."

WHY THE GATE EXISTS AT ALL, which decides how it must fail. Either kind of new
grammar is a REQUEST THAT THE ENGINE DO SOMETHING. A chain's `fallbacks`,
identity, signatures and pricing ask it to advance candidates and emit the
versioned events this repository projects; `config_options` asks it, after
`session/new` and before the first prompt, to read the agent's advertised
`configOptions` and set each requested one. An engine that implements neither
reads the configuration, ignores the parts it does not know, and runs the node
on whatever single adapter and model it would have chosen anyway -- a green run
that silently skipped the whole feature, with the configuration saying
otherwise and nothing in the record disagreeing. There is no symptom to notice
later, which is why the refusal has to happen before the claim.

THEREFORE IT FAILS CLOSED WHEN IT CANNOT OBSERVE ITS INPUT. An unreachable
factory, a server that answers nothing useful, and a server that genuinely
lacks the capability are ONE answer here: "not advertised". The alternative --
proceeding when the capability list is unreadable -- is the fail-open gauge
this repository's own agent instructions single out: blinding the input turns
a refusal into a pass, and the record it leaves reads like a healthy dispatch
rather than like an unanswered question.

AND IT IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE. The capability reader is
a CALLABLE, not a value, so a dispatch whose nodes are all LEGACY -- no
identity, no signature, no pricing, no non-empty `fallbacks`, which is every
dispatch in this fleet today -- performs no round trip at all. That is why the
obligation is computed first and the reader called second; swapping the two
would make every dispatch pay for an answer almost none of them use.

THE TWO ARMS ARE ONE ENTRY POINT, AND THAT IS DELIBERATE. Published as two
functions, the ORDER between their refusals would live at the call site, where
nothing tests it, and each caller would be free to build its own capability
reader -- two round trips per dispatch, and two answers nothing proves agree.
Composed here, the dispatch asks once and is told about the BASE capability
first, which is the deployment an operator actually has to perform:
`config_options` can only ride a chain that is already new-grammar-enabled, so
naming the narrower string to a factory missing both would send them after a
capability the engine cannot gain on its own.

BOTH POSITIONS COUNT. A fallback carrying `config_options` needs the
capability exactly as a primary does, because the handler configures whichever
candidate it actually runs. Gating only the primary would admit a chain whose
second candidate the server cannot configure, and that failure surfaces
mid-run, after the first candidate has already been spent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain

__all__: list[str] = [
    "CONFIG_OPTIONS_CAPABILITY",
    "FALLBACK_CHAIN_CAPABILITY",
    "acp_capability_refusal",
]

FALLBACK_CHAIN_CAPABILITY = "acp.fallback_chain.v1"
CONFIG_OPTIONS_CAPABILITY = "acp.candidate_config_options.v1"


def acp_capability_refusal(
    *,
    chains: Mapping[str, AcpNodeChain],
    factory_name: str,
    capabilities: Callable[[], frozenset[str] | None],
) -> str | None:
    """Refuse a new-grammar chain the resolved factory cannot honour.

    Returns `None` when every node is legacy or every owed capability is
    advertised; otherwise an actionable refusal naming the nodes, the factory
    and the one capability string to deploy, which the caller routes as a
    failed dispatch before any claim is taken.

    THE ENABLED SET DECIDES WHETHER TO READ AT ALL, and it is sufficient: a
    chain carrying `config_options` is enabled by construction -- the options
    only reach a chain through the structured form, and a fallback carrying
    them makes `fallbacks` non-empty -- so the base obligation subsumes the
    narrower one and no options-carrying chain can slip past an enabled-set
    guard.
    """
    enabled = sorted(node for node, chain in chains.items() if chain.enabled)
    if not enabled:
        return None
    advertised = capabilities()
    cause = _cause(advertised=advertised)
    if _absent(advertised=advertised, capability=FALLBACK_CHAIN_CAPABILITY):
        return _grammar_refusal(nodes=enabled, factory_name=factory_name, cause=cause)
    requesting = sorted(node for node, chain in chains.items() if _requests_options(chain=chain))
    if requesting and _absent(advertised=advertised, capability=CONFIG_OPTIONS_CAPABILITY):
        return _options_refusal(nodes=requesting, factory_name=factory_name, cause=cause)
    return None


def _absent(*, advertised: frozenset[str] | None, capability: str) -> bool:
    """Whether the factory has NOT confirmed this capability -- fail closed.

    An unreadable list and a list without the string are one answer, because
    the question the gate asks is "has this engine told us it can do this",
    and silence is not a yes.
    """
    return advertised is None or capability not in advertised


def _requests_options(*, chain: AcpNodeChain) -> bool:
    """Whether any candidate of this chain asks for an in-protocol option."""
    return bool(chain.config_options) or any(
        candidate.config_options for candidate in chain.fallbacks
    )


def _cause(*, advertised: frozenset[str] | None) -> str:
    """WHY a capability could not be confirmed, in the refusal's own words.

    The two causes are separated because the remedies are different and an
    operator cannot tell them apart from the outcome: a server that advertised
    a list without the capability needs a deployment, while a server whose
    capabilities could not be read may simply be unreachable right now.
    """
    if advertised is None:
        return "its capabilities could not be read"
    return f"it advertises only: {', '.join(sorted(advertised)) or '(nothing)'}"


def _grammar_refusal(*, nodes: list[str], factory_name: str, cause: str) -> str:
    """The BASE refusal: this engine does not implement ordered candidates."""
    return (
        f"ACP node(s) {', '.join(nodes)} declare new fallback-chain grammar (an identity, "
        f"availability signature, pricing table or non-empty fallbacks array); factory "
        f"{factory_name!r} does not advertise {FALLBACK_CHAIN_CAPABILITY} ({cause}). Deploy a "
        f"factory build carrying that capability, or remove the new-grammar fields from those "
        f"nodes to dispatch on the legacy single-adapter posture"
    )


def _options_refusal(*, nodes: list[str], factory_name: str, cause: str) -> str:
    """The NARROWER refusal: this engine advances candidates but cannot configure one."""
    return (
        f"ACP node(s) {', '.join(nodes)} declare a structured candidate whose agent takes "
        f"its model in-protocol, so the chain carries config_options; factory {factory_name!r} "
        f"does not advertise {CONFIG_OPTIONS_CAPABILITY} ({cause}). Deploy a factory build "
        f"carrying that capability, or configure those nodes with an agent whose catalog entry "
        f"declares an environment or argument mapping instead"
    )
