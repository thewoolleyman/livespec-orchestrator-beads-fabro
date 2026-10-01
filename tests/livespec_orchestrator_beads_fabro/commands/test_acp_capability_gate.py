"""The factory-capability gate on a chain carrying ACP new grammar.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority". Scenario 127's "New grammar is version-gated against the resolved
factory" is the whole-gate case -- "Given a node carries identity, signature,
pricing, or a non-empty fallback field / When ... the resolved factory server
lacks the pinned Fabro capability / Then dispatch refuses before claim or run
creation" -- and the section's "In-protocol model and effort selection" clause
is the narrower second arm: "The Fabro server MUST advertise the additive
capability `acp.candidate_config_options.v1` alongside `acp.fallback_chain.v1`,
and the Dispatcher MUST refuse before claim a chain carrying `config_options`
when the resolved factory server does not advertise it, exactly as the existing
capability gate does."

THE GATE FAILS CLOSED WHEN IT CANNOT OBSERVE ITS INPUT, and that is asserted
in its own right, for both arms. A capability gauge that passes when the
capability list is unreadable is the standing temptation this repository's own
agent instructions name: blinding the input converts a refusal into a pass, and
the resulting record reads as a healthy dispatch. An unreachable factory and a
factory that genuinely lacks the capability are both "not advertised", so both
refuse.

THE GAUGE IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE, and that is asserted
too, because it is the half that keeps the gate free. Only a NEW-GRAMMAR chain
needs the capability; a legacy node entry -- no identity, no signature, no
pricing, no non-empty `fallbacks` -- is the byte-identical v107 posture the
first acceptance condition protects, so reading the factory's capability list
on one would add a network round trip per dispatch for an answer nothing
consumes. The reader is therefore passed as a CALLABLE and the legacy case
asserts it was never called -- a property no assertion about the returned value
could establish.

THE TWO ARMS ARE ORDERED, AND THE ORDER IS ASSERTED. `config_options` can only
ride a chain that is already new-grammar-enabled, so a factory advertising
NEITHER string owes the base capability first: that is the deployment an
operator actually has to perform, and naming the narrower string first would
send them after a capability that cannot arrive on its own. Each arm is
therefore exercised with the other arm's capability PRESENT, so a passing
assertion is about the arm it names rather than about whichever refusal
happened to fire.

BOTH POSITIONS CARRY THE OBLIGATION. A fallback carrying `config_options`
needs the capability exactly as a primary does, because the handler sets the
options for whichever candidate it runs. A gate reading only the primary would
pass a chain whose second candidate the server cannot configure, and the
failure would surface mid-run after the first candidate had already been
spent.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_CAPABILITY = "acp.candidate_config_options.v1"
_FALLBACK_CAPABILITY = "acp.fallback_chain.v1"
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
        chains=_chains(entry=entry), factory_name=_FACTORY, capabilities=reader
    )


def test_a_new_grammar_chain_refuses_when_the_factory_lacks_the_fallback_capability() -> None:
    """The base arm: the refusal names the node, the factory and the string.

    The entry carries identity and a resolved model but NO `config_options` --
    `claude-acp` takes its model in the environment -- so the only obligation it
    owes is the base `acp.fallback_chain.v1` one, and this case cannot pass by
    way of the narrower arm.
    """
    reader = _Reader(capabilities=frozenset({"some.unrelated.capability.v1"}))

    refusal = _refusal(entry=dict(_ENV_ENTRY), reader=reader)

    assert refusal is not None
    assert _FALLBACK_CAPABILITY in refusal
    assert _FACTORY in refusal
    assert _NODE in refusal
    assert reader.calls == 1


def test_a_new_grammar_chain_proceeds_when_the_factory_advertises_the_capability() -> None:
    """The base arm's control: the gate refuses the MISSING string, not the grammar."""
    reader = _Reader(capabilities=frozenset({_FALLBACK_CAPABILITY}))

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None
    assert reader.calls == 1


def test_an_unobservable_capability_list_refuses_the_new_grammar() -> None:
    """Fail CLOSED on the base arm: "could not establish" is not "advertised"."""
    reader = _Reader(capabilities=None)

    refusal = _refusal(entry=dict(_ENV_ENTRY), reader=reader)

    assert refusal is not None
    assert _FALLBACK_CAPABILITY in refusal
    assert "could not be read" in refusal


def test_a_non_empty_fallback_field_alone_opts_the_node_into_the_gate() -> None:
    """`fallbacks` is new grammar on its own, with no identity field in sight.

    The contract's enabling predicate is identity OR signature OR pricing OR a
    NON-EMPTY fallback array, and a chain whose only new-grammar field is the
    array is the one spelling a gate keyed on identity alone would wave through.
    """
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(entry={**_LEGACY_ENTRY, "fallbacks": [dict(_ENV_ENTRY)]}, reader=reader)

    assert refusal is not None
    assert _FALLBACK_CAPABILITY in refusal


def test_a_primary_carrying_options_refuses_when_the_factory_lacks_the_capability() -> None:
    """The refusal names the factory and the capability string it wants.

    The base capability IS advertised here, which is what isolates the arm: a
    reader advertising neither string would refuse on the base arm and this
    assertion would pass without the narrower gate existing at all.
    """
    reader = _Reader(capabilities=frozenset({_FALLBACK_CAPABILITY}))

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert _FACTORY in refusal
    assert reader.calls == 1


def test_a_primary_carrying_options_proceeds_when_the_factory_advertises_it() -> None:
    """The control: the gate refuses the MISSING capability, not every chain."""
    reader = _Reader(capabilities=frozenset({_FALLBACK_CAPABILITY, _CAPABILITY}))

    assert _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader) is None
    assert reader.calls == 1


def test_an_unobservable_capability_list_refuses_rather_than_passing() -> None:
    """Fail CLOSED: "could not establish" is not "advertised"."""
    reader = _Reader(capabilities=None)

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _FACTORY in refusal


def test_a_fallback_carrying_options_is_gated_too() -> None:
    """A chain's later candidates carry the obligation exactly as its first does."""
    reader = _Reader(capabilities=frozenset({_FALLBACK_CAPABILITY}))

    refusal = _refusal(entry={**_ENV_ENTRY, "fallbacks": [dict(_PROTOCOL_ENTRY)]}, reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal


def test_a_factory_advertising_neither_string_is_told_the_base_one_first() -> None:
    """Ordering, asserted rather than left to the call site.

    `config_options` cannot ride a chain that is not already new-grammar-enabled,
    so a factory missing both strings needs the base deployment; naming only the
    narrower string would send an operator after a capability the engine cannot
    gain on its own.
    """
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _FALLBACK_CAPABILITY in refusal
    assert _CAPABILITY not in refusal


def test_a_legacy_chain_never_consults_the_gauge() -> None:
    """No obligation, no round trip -- asserted on the reader, not the answer.

    An assertion that the refusal is `None` would pass just as well against a
    gate that read the capability list on every dispatch and happened to find
    the capability; only the call count separates the two. The entry is the
    LEGACY spelling, because since the base arm exists every new-grammar chain
    does owe a read.
    """
    reader = _Reader(capabilities=None)

    assert _refusal(entry=dict(_LEGACY_ENTRY), reader=reader) is None
    assert reader.calls == 0
