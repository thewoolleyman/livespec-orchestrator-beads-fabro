"""The factory-capability gate on a chain carrying `config_options`.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "In-protocol model and effort selection": "The Fabro server MUST
advertise the additive capability `acp.candidate_config_options.v1` alongside
`acp.fallback_chain.v1`, and the Dispatcher MUST refuse before claim a chain
carrying `config_options` when the resolved factory server does not advertise
it, exactly as the existing capability gate does."

THE GATE FAILS CLOSED WHEN IT CANNOT OBSERVE ITS INPUT, and that is asserted
in its own right. A capability gauge that passes when the capability list is
unreadable is the standing temptation this repository's own agent instructions
name: blinding the input converts a refusal into a pass, and the resulting
record reads as a healthy dispatch. An unreachable factory and a factory that
genuinely lacks the capability are both "not advertised", so both refuse.

THE GAUGE IS NOT CONSULTED WHEN IT HAS NOTHING TO GATE, and that is asserted
too, because it is the half that keeps the gate free. Only a chain carrying
`config_options` needs the capability; every dispatch in this fleet today
carries none, so reading the factory's capability list on those would add a
network round trip per dispatch for an answer nothing consumes. The reader is
therefore passed as a CALLABLE and the no-options case asserts it was never
called -- a property no assertion about the returned value could establish.

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
_FACTORY = "hp"

_PROTOCOL_ENTRY: dict[str, Any] = {"agent": "glm-acp-agent", "model": "glm-5.2"}
_ENV_ENTRY: dict[str, Any] = {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}


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
    return _module(name="_acp_capability_gate").config_options_capability_refusal(
        chains=_chains(entry=entry), factory_name=_FACTORY, capabilities=reader
    )


def test_a_primary_carrying_options_refuses_when_the_factory_lacks_the_capability() -> None:
    """The refusal names the factory and the capability string it wants."""
    reader = _Reader(capabilities=frozenset({"acp.fallback_chain.v1"}))

    refusal = _refusal(entry=dict(_PROTOCOL_ENTRY), reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal
    assert _FACTORY in refusal
    assert reader.calls == 1


def test_a_primary_carrying_options_proceeds_when_the_factory_advertises_it() -> None:
    """The control: the gate refuses the MISSING capability, not every chain."""
    reader = _Reader(capabilities=frozenset({"acp.fallback_chain.v1", _CAPABILITY}))

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
    reader = _Reader(capabilities=frozenset())

    refusal = _refusal(entry={**_ENV_ENTRY, "fallbacks": [dict(_PROTOCOL_ENTRY)]}, reader=reader)

    assert refusal is not None
    assert _CAPABILITY in refusal


def test_a_chain_carrying_no_options_never_consults_the_gauge() -> None:
    """No obligation, no round trip -- asserted on the reader, not the answer.

    An assertion that the refusal is `None` would pass just as well against a
    gate that read the capability list on every dispatch and happened to find
    the capability; only the call count separates the two.
    """
    reader = _Reader(capabilities=None)

    assert _refusal(entry=dict(_ENV_ENTRY), reader=reader) is None
    assert reader.calls == 0
