"""The ONE factory capability an ACP chain still owes: `config_options`.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Because the Dispatcher renders exactly one literal adapter per node,
a new-grammar-enabled dispatch requires NO Fabro engine capability for fallback.
The Dispatcher MUST NOT refuse a dispatch because the resolved factory server
does not advertise a fallback-chain capability; the only engine capability gate
that remains is the `config_options` gate of "In-protocol model and effort
selection" below, which applies only to a dispatch whose selected candidates use
it." Scenario 127 states the same thing from the other side: "a resolved factory
server that advertises no fallback-chain capability does not refuse the
dispatch".

THE RETIRED ARM IS ASSERTED AS AN ADMISSION, not merely omitted. A gate that
still read the base string would refuse every fallback-enabled dispatch in this
fleet, and the refusal would look exactly like a factory that needs a deployment
-- so the clause is only honoured if an advertised set WITHOUT that string
admits. The case is run against a factory advertising an unrelated capability
AND against one advertising nothing at all, because the second is what a server
with no ACP support answers.

WHY THE ENGINE NO LONGER NEEDS IT. The Dispatcher now consumes the chain itself:
it chooses one candidate per node and writes that candidate's adapter in as the
node's only adapter, so the engine runs a single adapter with no knowledge of the
others. Ordered fallback happens BETWEEN runs, through provider-limit release and
re-dispatch, never inside one node visit. There is nothing left for an engine
capability to enable.

THE REMAINING ARM FAILS CLOSED WHEN IT CANNOT OBSERVE ITS INPUT, and that is
asserted in its own right. `config_options` asks the engine to read the agent's
advertised options and set each requested one after `session/new`; an engine that
cannot do it ignores the request and runs the node on whatever model it would
have chosen anyway -- a green run that silently skipped the request, with nothing
in the record disagreeing. So an unreachable factory and a factory that genuinely
lacks the capability are one answer: not advertised.

THE GAUGE IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE, and that is asserted on
the reader's CALL COUNT rather than on the returned value. An assertion that the
refusal is `None` would pass just as well against a gate that read the capability
list on every dispatch and happened to find the capability; only the call count
separates the two. Both the legacy spelling and a new-grammar chain whose agent
takes its model in the ENVIRONMENT owe no read at all, which is the second half
of what retiring the base arm buys.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_CAPABILITY = "acp.candidate_config_options.v1"
_RETIRED_CAPABILITY = "acp.fallback_chain.v1"
_FACTORY = "hp"
_NODE = "implement"

_PROTOCOL_ENTRY: dict[str, Any] = {"agent": "glm-acp-agent", "model": "glm-5.2"}
_ENV_ENTRY: dict[str, Any] = {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}
# No identity, no signature, no pricing, no `fallbacks`: the pre-feature
# spelling, which resolves to the empty chain and owes no capability at all.
_LEGACY_ENTRY: dict[str, Any] = {"command": "codex-acp", "args": ["--stdio"]}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _chains(*, entry: dict[str, Any]) -> Any:
    """One node's declared chain, through the real repository reader."""
    catalogs = _module(name="_acp_catalogs").builtin_catalogs()
    declared = _module(name="_acp_node_repository").repository_acp_chains(
        block={"acp_nodes": {"implement": entry}}, catalogs=catalogs
    )
    assert not isinstance(declared, str), declared
    return declared


class _Reader:
    """A recording capability reader, so "never consulted" is observable."""

    def __init__(self, *, capabilities: frozenset[str] | None) -> None:
        self.capabilities = capabilities
        self.calls = 0

    def __call__(self) -> frozenset[str] | None:
        self.calls += 1
        return self.capabilities


def _selection(*, entry: dict[str, Any]) -> Any:
    """This node's selection with NOTHING held, i.e. position zero.

    The gate reads the SELECTED candidate, so every case here states the
    selection explicitly rather than handing over a chain. Position zero is the
    right one for all of them: each varies the factory's CAPABILITY answer and
    not which candidate the dispatch rendered. The selection semantics
    themselves -- a selected fallback gating, an unselected one never gating --
    are covered end to end through the real resolution path in
    `test_acp_selected_candidate_options_gate.py`.
    """
    schema = _module(name="_acp_candidate_schema")
    adapters = _module(name="_acp_node_adapters")
    selection = _module(name="_acp_node_selection")
    chain = _chains(entry=entry)[_NODE]
    return {
        _NODE: selection.SelectedAcpCandidate(
            node=_NODE,
            index=0,
            candidate=schema.AcpCandidate(
                adapter=adapters.AcpAdapter(command="acp"),
                identity=chain.identity,
                agent_id=chain.agent_id,
                config_options=chain.config_options,
            ),
            selection_identity="sel-0123456789abcdef",
            primary_generation="gen-0123456789abcdef",
            full_chain="chain-0123456789abcdef",
            skipped=(),
        )
    }


def _refusal(*, entry: dict[str, Any], reader: _Reader) -> str | None:
    """One gate call, through the module's DECLARED public surface.

    The `__all__` assertion is not ceremony: this package requires every module
    to enumerate its public surface there, so a gate arm reachable only as an
    undeclared attribute is not a surface the Dispatcher may wire. Asserting it
    here keeps every case below from passing against a half-declared module.
    """
    gate = _module(name="_acp_capability_gate")
    assert "acp_capability_refusal" in gate.__all__, sorted(gate.__all__)
    return gate.acp_capability_refusal(
        selected=_selection(entry=entry), factory_name=_FACTORY, capabilities=reader
    )


def test_a_new_grammar_chain_is_admitted_without_the_fallback_chain_capability() -> None:
    """The retired arm: no engine capability is owed for ordered fallback.

    The entry carries identity and a resolved model but NO `config_options` --
    `claude-acp` takes its model in the environment -- so the only capability it
    could ever owe is the retired one, and an admission here cannot be an
    accident of the remaining arm.
    """
    reader = _Reader(capabilities=frozenset({"some.unrelated.capability.v1"}))

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None


def test_a_factory_advertising_nothing_at_all_still_admits_ordered_fallback() -> None:
    """The same claim against an engine advertising an EMPTY capability set.

    This is what a server with no ACP capability surface answers, and it is the
    shape a gate keyed on "the string is absent" refuses most readily.
    """
    reader = _Reader(capabilities=frozenset())

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None


def test_a_non_empty_fallback_field_alone_is_admitted_too() -> None:
    """`fallbacks` is new grammar on its own, and owes no capability either.

    The contract's enabling predicate is identity OR signature OR pricing OR a
    NON-EMPTY fallback array. A chain whose only new-grammar field is the array
    is the spelling a retired gate keyed on the array would still refuse.
    """
    reader = _Reader(capabilities=frozenset())

    assert _refusal(entry={**_LEGACY_ENTRY, "fallbacks": [dict(_ENV_ENTRY)]}, reader=reader) is None


def test_an_unreadable_capability_list_does_not_refuse_ordered_fallback() -> None:
    """An unreachable factory refuses nothing when nothing is owed.

    Fail-closed is a property of the capability that IS owed; it cannot
    manufacture an obligation that the clause retired.
    """
    reader = _Reader(capabilities=None)

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None


def test_a_chain_carrying_options_refuses_when_the_factory_lacks_the_capability() -> None:
    """The remaining arm: the refusal names the factory and the capability string.

    The retired string is asserted ABSENT from the refusal, against a factory
    that advertises neither: that is the one combination a surviving base arm
    would answer differently, so the assertion names the capability an operator
    is sent to deploy rather than merely that some refusal fired.
    """
    reader = _Reader(capabilities=frozenset({"some.unrelated.capability.v1"}))

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert _RETIRED_CAPABILITY not in refusal
    assert _FACTORY in refusal
    assert _NODE in refusal
    assert reader.calls == 1


def test_a_chain_carrying_options_proceeds_when_the_factory_advertises_it() -> None:
    """The control: the gate refuses the MISSING capability, not every chain."""
    reader = _Reader(capabilities=frozenset({_CAPABILITY}))

    assert _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader) is None
    assert reader.calls == 1


def test_an_unobservable_capability_list_refuses_an_options_chain() -> None:
    """Fail CLOSED on the arm that is owed: "could not establish" is not "advertised"."""
    reader = _Reader(capabilities=None)

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert "could not be read" in refusal


def test_an_advertised_set_without_the_capability_says_what_it_did_advertise() -> None:
    """The two causes are separated because the remedies differ.

    A server that answered a list without the capability needs a deployment; one
    whose capabilities could not be read may simply be down, and an operator
    cannot tell them apart from the outcome.
    """
    reader = _Reader(capabilities=frozenset({"some.unrelated.capability.v1"}))

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert "some.unrelated.capability.v1" in refusal
    assert "could not be read" not in refusal


def test_an_empty_advertised_set_is_reported_as_nothing() -> None:
    """An engine that advertised an empty list says so, rather than reading blank."""
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert "(nothing)" in refusal


def test_a_chain_whose_unselected_fallback_carries_options_is_not_gated() -> None:
    """An UNSELECTED fallback's options never gate -- and owe no round trip.

    `contracts.md` ends the clause saying so in as many words: "an unselected
    fallback's options never gate a dispatch". The Dispatcher renders exactly
    one candidate per node and the engine never learns the others exist, so a
    fallback's request is one no engine is asked to honour on THIS dispatch; a
    later dispatch that actually selects it is gated then, when the obligation
    is real. Gating it now would refuse a dispatch that would have run
    correctly, naming a capability the rendered configuration does not need.

    Asserted on the CALL COUNT as well as the answer, because a gate that read
    the list and happened to find the capability would also return `None`.
    """
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(entry={**_ENV_ENTRY, "fallbacks": [dict(_PROTOCOL_ENTRY)]}, reader=reader)

    assert refusal is None
    assert reader.calls == 0


def test_a_legacy_chain_never_consults_the_gauge() -> None:
    """No obligation, no round trip -- asserted on the reader, not the answer."""
    reader = _Reader(capabilities=None)

    assert _refusal(entry=dict(_LEGACY_ENTRY), reader=reader) is None
    assert reader.calls == 0


def test_a_new_grammar_chain_without_options_never_consults_the_gauge_either() -> None:
    """The second half of retiring the base arm: no read for the common case.

    Every dispatch in this fleet resolves an environment-mechanism agent, so a
    gate that still read the capability list for any new-grammar chain would add
    a network round trip per dispatch for an answer nothing consumes.
    """
    reader = _Reader(capabilities=None)

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None
    assert reader.calls == 0
