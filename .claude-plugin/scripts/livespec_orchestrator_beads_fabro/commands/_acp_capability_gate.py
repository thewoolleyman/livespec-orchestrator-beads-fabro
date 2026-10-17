"""The ONE factory capability an ACP chain still owes: `config_options`.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Because the Dispatcher renders exactly one literal adapter per node,
a new-grammar-enabled dispatch requires NO Fabro engine capability for fallback.
The Dispatcher MUST NOT refuse a dispatch because the resolved factory server
does not advertise a fallback-chain capability; the only engine capability gate
that remains is the `config_options` gate of "In-protocol model and effort
selection" below, which applies only to a dispatch whose selected candidates use
it."

WHY THE FALLBACK-CHAIN ARM IS GONE, which is the whole shape of this module. It
existed while ordered fallback was something the ENGINE did: a chain's
`fallbacks`, identity, signatures and pricing asked it to advance candidates and
emit versioned events, and an engine that implemented none of that read the
configuration, ignored the parts it did not know, and ran the node on whatever
single adapter it would have chosen anyway -- a green run that silently skipped
the whole feature. Spec v127 moved the consumption to the DISPATCHER: it selects
one candidate per node and writes that candidate's adapter in as the node's only
adapter, so the engine runs one adapter with no knowledge of the others, and
ordered fallback happens BETWEEN runs through provider-limit release and
re-dispatch. There is nothing left for an engine capability to enable, so
refusing on its absence would refuse every fallback-enabled dispatch in this
fleet for a deployment that buys nothing.

THE REMAINING ARM IS A REQUEST THAT THE ENGINE DO SOMETHING, which is why it
survives and why it must fail closed. `config_options` asks the engine, after
`session/new` and before the first prompt, to read the agent's advertised
`configOptions` and set each requested one. An engine that cannot do it ignores
the request and runs the node on its own default model -- the same invisible
green as before, with the configuration saying otherwise and nothing in the
record disagreeing. So an unreachable factory, a server that answers nothing
useful, and a server that genuinely lacks the capability are ONE answer here:
"not advertised". Proceeding when the capability list is unreadable is the
fail-open gauge this repository's own agent instructions single out -- blinding
the input turns a refusal into a pass, and the record it leaves reads like a
healthy dispatch rather than like an unanswered question.

AND IT IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE. The capability reader is a
CALLABLE, not a value, so a dispatch whose candidates all take their model in
the environment or on a command line -- which is every dispatch in this fleet
today -- performs no round trip at all. That is why the obligation is computed
first and the reader called second; swapping the two would make every dispatch
pay for an answer almost none of them use.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from livespec_orchestrator_beads_fabro.commands._acp_node_selection import SelectedAcpCandidate

__all__: list[str] = [
    "CONFIG_OPTIONS_CAPABILITY",
    "acp_capability_refusal",
]

CONFIG_OPTIONS_CAPABILITY = "acp.candidate_config_options.v1"


def acp_capability_refusal(
    *,
    selected: Mapping[str, SelectedAcpCandidate],
    factory_name: str,
    capabilities: Callable[[], frozenset[str] | None],
) -> str | None:
    """Refuse a SELECTED candidate the resolved factory cannot configure.

    Returns `None` when no node's selected candidate asks for an in-protocol
    option or the capability is advertised; otherwise an actionable refusal
    naming the nodes, the factory and the one capability string to deploy, which
    the caller routes as a failed dispatch before any claim is taken.

    THE SELECTION AND NEVER THE WHOLE CHAIN. `contracts.md` ends the clause with
    "an unselected fallback's options never gate a dispatch", and the reason is
    that the Dispatcher renders exactly ONE candidate per node: a fallback's
    `config_options` is a request no engine is asked to honour on this dispatch,
    so refusing on it refuses a dispatch that would have run correctly -- while
    naming a capability the rendered configuration does not need. The cost would
    land on exactly the configuration this feature encourages, a
    protocol-configured fallback behind a healthy environment-mechanism primary,
    which would refuse every dispatch of that node for a candidate it was never
    going to run.
    """
    requesting = sorted(node for node, one in selected.items() if one.candidate.config_options)
    if not requesting:
        return None
    advertised = capabilities()
    if advertised is not None and CONFIG_OPTIONS_CAPABILITY in advertised:
        return None
    return _options_refusal(
        nodes=requesting, factory_name=factory_name, cause=_cause(advertised=advertised)
    )


def _cause(*, advertised: frozenset[str] | None) -> str:
    """WHY the capability could not be confirmed, in the refusal's own words.

    The two causes are separated because the remedies are different and an
    operator cannot tell them apart from the outcome: a server that advertised
    a list without the capability needs a deployment, while a server whose
    capabilities could not be read may simply be unreachable right now.
    """
    if advertised is None:
        return "its capabilities could not be read"
    return f"it advertises only: {', '.join(sorted(advertised)) or '(nothing)'}"


def _options_refusal(*, nodes: list[str], factory_name: str, cause: str) -> str:
    """This engine runs the adapter it is given but cannot configure its session."""
    return (
        f"ACP node(s) {', '.join(nodes)} declare a structured candidate whose agent takes "
        f"its model in-protocol, so the chain carries config_options; factory {factory_name!r} "
        f"does not advertise {CONFIG_OPTIONS_CAPABILITY} ({cause}). Deploy a factory build "
        f"carrying that capability, or configure those nodes with an agent whose catalog entry "
        f"declares an environment or argument mapping instead"
    )
