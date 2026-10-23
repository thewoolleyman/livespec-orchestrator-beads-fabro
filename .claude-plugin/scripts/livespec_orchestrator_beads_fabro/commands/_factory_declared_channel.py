"""The credential transport ONE factory declares, across BOTH of its sources.

Split out of `_dispatcher_secret_channel` when the host factory registry gained
client settings. That module owns what a transport MEANS — the two this build
speaks, the vault keying, the bundle rewrite and the refusal — and this owns the
narrower question of what the configuration DECLARES, which now has two possible
answers for one factory: the committed `dispatcher.factories` entry, and the
registry entry a registry-backed factory resolves through.

WHY THE RAW DECLARATION IS RETURNED RATHER THAN A TRANSPORT. Absence and an
explicitly malformed value are different security answers, and only absence
selects the pinned engine's inline default. A reader that resolved the value
here would have to collapse `null`, `""` and a misspelled transport onto
something, and the only available something is that default — which on a
Petri-era server persists a literal credential in an immutable workflow version.
So the sentinel travels, and the grade stays where the transports are known.

WHY THE MERGE IS APPLIED HERE RATHER THAN BY THE CALLER. `resolve_secret_channel`
is asked for a factory BY NAME and never sees a resolved `FactoryTarget`, so a
caller-supplied registry side would be a parameter every one of its call sites
has to remember — and a call site that forgot would get the committed answer,
silently, which for a fleet repository committing no `secret_channel` is the
inline default on a factory the registry says speaks something else. Resolving
the registry from the same block the committed side comes out of is what makes
the two sources one answer with one authority.

WHY THE FLEET SELECTION IS CONSULTED. A factory reached through the reserved
`dispatcher.default_factory` value is registry-backed whether or not the
repository declares it, so asking only the entry's own `registry` key would
leave every fleet-default factory taking the committed answer for a key no
fleet repository commits. `_factory_default.fleet_selection` is the same reader
`_config` uses, rather than a second test of the reserved value, because two
accounts of "is this name the one `fleet` reaches" would disagree exactly when
the designation moved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._factory_client_settings import (
    FACTORY_SECRET_CHANNEL_KEY,
    effective_factory_client_settings,
)
from livespec_orchestrator_beads_fabro.commands._factory_default import fleet_selection
from livespec_orchestrator_beads_fabro.commands._factory_registry import (
    factory_registry_from_entry,
)

__all__: list[str] = [
    "DECLARATION_ABSENT",
    "ChannelDeclaration",
    "declared_factory_channel",
]

# "No source declared this key", kept apart from every value either source could
# hold. `None` cannot say it: an operator who wrote `"secret_channel": null`
# wrote something, and the whole reason this sentinel exists is that the grade
# downstream must refuse that while admitting a genuine absence.
DECLARATION_ABSENT = object()

_FACTORIES_KEY = "factories"


@dataclass(frozen=True, kw_only=True)
class ChannelDeclaration:
    """One factory's effective raw transport declaration, and which source wrote it.

    The source travels WITH the value because the grade downstream refuses an
    unrecognised transport by naming the key and a remedy, and the remedy
    differs: a committed value is a line in the governed repository's own
    `.livespec.jsonc` and a registry-supplied one is host state the fleet's
    provisioning renders. The value itself reaches the grade on one field either
    way — that identity is how a registry-backed factory gets the registry's
    transport with no consumer changing — so this field is the only thing left
    that can tell the two apart.

    `registry_path` is None for a committed value and for the absent sentinel
    alike, and the collapse is safe because the grade returns on the sentinel
    before it reads the source: "the registry supplied no value" and "nobody
    supplied one" have the same remedy, which is that there is nothing to fix.
    """

    value: object
    registry_path: str | None = None


def declared_factory_channel(*, block: Mapping[str, object], factory: str) -> ChannelDeclaration:
    """One factory's EFFECTIVE raw transport declaration, or the absent sentinel.

    The committed entry wins when it declares the key, and otherwise the
    registry entry does — the same per-key rule every client setting takes, and
    applied through the same merger, so a transport cannot acquire a precedence
    of its own.

    The SOURCE is read off that same merge rather than re-derived from the two
    entries here, for the reason the merger's own docstring gives: a second
    account of the precedence would disagree with the first in the direction
    nothing announces, and here the disagreement would surface as a refusal
    sending an operator to the wrong file.
    """
    entry = _committed_entry(block=block, factory=factory)
    registry = factory_registry_from_entry(
        entry=entry,
        name=factory,
        fleet=fleet_selection(block=_dispatcher_block(block=block), name=factory),
    )
    client = effective_factory_client_settings(entry=entry, registry=registry.client)
    if not client.declares_secret_channel:
        return ChannelDeclaration(value=DECLARATION_ABSENT)
    return ChannelDeclaration(
        value=client.secret_channel,
        registry_path=(
            registry.path if FACTORY_SECRET_CHANNEL_KEY in client.registry_sourced else None
        ),
    )


def _committed_entry(*, block: Mapping[str, object], factory: str) -> dict[str, Any]:
    """One named `dispatcher.factories` entry, or `{}` when it is not declared.

    An undeclared name is not a fault here for the reason `_config._factory_entry`
    gives: the factory a fleet default names need not be declared at all, and the
    implicit single-factory target is exactly this case.
    """
    factories = _dispatcher_block(block=block).get(_FACTORIES_KEY)
    if not isinstance(factories, dict):
        return {}
    entry = cast("dict[str, Any]", factories).get(factory)
    if not isinstance(entry, dict):
        return {}
    return cast("dict[str, Any]", entry)


def _dispatcher_block(*, block: Mapping[str, object]) -> dict[str, Any]:
    """The dispatcher block as the factory readers want it, never `None`.

    A widening cast rather than a conversion: the callers above hand this the
    block they already hold, and `Mapping[str, object]` is the type the transport
    resolution has always taken. Returning `{}` for anything else keeps a caller
    that holds no block on the absent answer rather than raising inside a reader
    whose whole output is a declaration.
    """
    return cast("dict[str, Any]", block) if isinstance(block, dict) else {}
