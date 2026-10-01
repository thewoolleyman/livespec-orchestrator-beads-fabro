"""The factory-capability gate on a chain carrying `config_options`.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "In-protocol model and effort selection": "The Fabro server MUST
advertise the additive capability `acp.candidate_config_options.v1` alongside
`acp.fallback_chain.v1`, and the Dispatcher MUST refuse before claim a chain
carrying `config_options` when the resolved factory server does not advertise
it, exactly as the existing capability gate does."

WHY THE GATE EXISTS AT ALL, which decides how it must fail. A chain carrying
`config_options` is a REQUEST THAT THE HANDLER DO SOMETHING: after `session/new`
and before the first prompt it must read the agent's advertised `configOptions`
and set each requested one. A server that does not implement that reads the
chain, ignores the object, and runs the agent on whatever model it chooses --
a green run on the wrong model, with the configuration saying otherwise and
nothing in the record disagreeing. There is no symptom to notice later, which
is why the refusal has to happen before the claim.

THEREFORE IT FAILS CLOSED WHEN IT CANNOT OBSERVE ITS INPUT. An unreachable
factory, a server that answers nothing useful, and a server that genuinely
lacks the capability are ONE answer here: "not advertised". The alternative --
proceeding when the capability list is unreadable -- is the fail-open gauge
this repository's own agent instructions single out: blinding the input turns
a refusal into a pass, and the record it leaves reads like a healthy dispatch
rather than like an unanswered question.

AND IT IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE. The capability reader is
a CALLABLE, not a value, so a dispatch whose chains carry no `config_options`
-- every dispatch in this fleet today -- performs no round trip at all. That
is why the obligation is computed first and the reader called second; swapping
the two would make every dispatch pay for an answer almost none of them use.

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
    "config_options_capability_refusal",
]

CONFIG_OPTIONS_CAPABILITY = "acp.candidate_config_options.v1"


def config_options_capability_refusal(
    *,
    chains: Mapping[str, AcpNodeChain],
    factory_name: str,
    capabilities: Callable[[], frozenset[str] | None],
) -> str | None:
    """Refuse a `config_options`-carrying chain the factory cannot configure.

    Returns `None` when there is nothing to gate or the capability is
    advertised; otherwise an actionable refusal naming the nodes, the factory
    and the capability string, which the caller routes as a failed dispatch
    before any claim is taken.
    """
    requesting = sorted(node for node, chain in chains.items() if _requests_options(chain=chain))
    if not requesting:
        return None
    advertised = capabilities()
    if advertised is not None and CONFIG_OPTIONS_CAPABILITY in advertised:
        return None
    return _refusal(requesting=requesting, factory_name=factory_name, advertised=advertised)


def _requests_options(*, chain: AcpNodeChain) -> bool:
    """Whether any candidate of this chain asks for an in-protocol option."""
    return bool(chain.config_options) or any(
        candidate.config_options for candidate in chain.fallbacks
    )


def _refusal(*, requesting: list[str], factory_name: str, advertised: frozenset[str] | None) -> str:
    """The refusal, naming WHY the capability could not be confirmed.

    The two causes are separated because the remedies are different and an
    operator cannot tell them apart from the outcome: a server that advertised
    a list without this capability needs a deployment, while a server whose
    capabilities could not be read may simply be unreachable right now.
    """
    cause = (
        "its capabilities could not be read"
        if advertised is None
        else f"it advertises only: {', '.join(sorted(advertised)) or '(nothing)'}"
    )
    return (
        f"ACP node(s) {', '.join(requesting)} declare a structured candidate whose agent takes "
        f"its model in-protocol, so the chain carries config_options; factory {factory_name!r} "
        f"does not advertise {CONFIG_OPTIONS_CAPABILITY} ({cause}). Deploy a factory build "
        f"carrying that capability, or configure those nodes with an agent whose catalog entry "
        f"declares an environment or argument mapping instead"
    )
