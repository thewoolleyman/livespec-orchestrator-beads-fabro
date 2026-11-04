"""The host registry a REGISTRY-BACKED factory's address is resolved from.

Split out of `_config` for the same reason `_factory_environment`,
`_node_timeouts` and `_workflow_variants` are: what a `dispatcher.factories`
entry's `registry` key MEANS belongs beside its own reader rather than inside
the general connection-resolution module. `_config._factory_target_for` is the
config-reading seam that feeds it, and `_dispatcher_factory_registry` is where
the reading is GRADED — the pre-claim refusal of a registry that does not
resolve.

WHY THE KEY EXISTS. A committed `server` value binds a factory to a MACHINE, so
moving that factory to another machine is a change to every governed
repository's `.livespec.jsonc` — a fleet-wide commit, a release and a plugin
refresh, for a fact the provisioning inventory already holds. A registry-backed
entry names only the factory; the machine is host state the fleet's provisioning
renders, so a move is a provisioning change and nothing in any repository is
touched. No committed file in a governed repository writes the registry.

WHY AN UNRESOLVABLE REGISTRY MUST BE READ AS A REFUSAL AND NOT AS AN ANSWER.
`FactoryTarget.server` of `None` already means something, and it means the
AMBIENT LOCAL Fabro target: that is how an unconfigured repository preserves the
bare CLI's behaviour. So a reading that folded "the registry did not resolve"
into `None` would route the dispatch to whatever Fabro the DISPATCHING host
runs — a run created on the wrong machine, with no error, and with the item's
own record naming a factory the work never reached. The reading therefore keeps
`detail` beside `server`: `declared` with no server and a detail IS the
unresolvable state, and it is the one shape the grade refuses.

WHY ONLY THE SELECTED ENTRY IS VALIDATED. The registry is host state rendered
from an inventory that covers the whole fleet, so at any moment it may hold an
entry for a factory this repository never dispatches to, written in a shape this
build does not expect. Validating the whole table would make one unrelated
entry refuse every dispatch on the host. Resolution reads the selected name and
nothing else.

WHY `registry` IS TESTED FOR `True` AND NOT FOR MEMBERSHIP, which is the
opposite of what `_factory_environment` does with its own key. `environment`
carries a VALUE, so an operator who wrote `null` wrote something, and reporting
that as an absent key would hand it the conforming path. `registry` carries a
DECISION, and the clause ratifies exactly one way of taking it — `"registry":
true`. Anything else is an entry that is not registry-backed, which is a
complete answer: it keeps the pre-clause meaning, where `server` decides. A
refusal for some other spelling is not ratified here, and inventing one would
make this reader assert something the clause does not.

WHY THE FLEET DEFAULT IS READ HERE RATHER THAN BESIDE THE DEFAULT-FACTORY
DERIVATION. The registry's top-level `default` key designates a factory of this
same file, so answering "which factory does `fleet` name" is a reading of the
registry and shares every one of its five unreadable states with the per-entry
reading — absent, unreadable, undecodable, unparseable, not an object. Reading
it in `_factory_default` would mean a second opener of the same file with a
second account of what makes it unusable, and the two accounts would disagree
in the direction nothing announces: one of them resolving while the other
refuses.

WHY A FLEET-SELECTED FACTORY IS REGISTRY-BACKED WHATEVER ITS ENTRY SAYS. The
clause makes the factory the fleet default names an IMPLICITLY DECLARED entry of
the repository, and requires every factory selected through `fleet` to resolve
its addresses through the registry "including a factory the repository also
declares". So `fleet` is an input to the reading rather than a question the
entry answers: the common case has no committed entry at all, and the case that
does must not be allowed to supply a second address. That is why a committed
`server` or `docker_host` beside a fleet selection is the same CONFLICT a
`"registry": true` entry carrying one is, and is refused the same way.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._factory_client_settings import (
    NO_FACTORY_CLIENT_SETTINGS,
    FactoryClientSettings,
    factory_client_settings_from_entry,
)

__all__: list[str] = [
    "DEFAULT_REGISTRY_PATH",
    "FLEET_DEFAULT_FACTORY",
    "NO_FACTORY_REGISTRY",
    "REGISTRY_DEFAULT_KEY",
    "REGISTRY_KEY",
    "REGISTRY_PATH_ENV_VAR",
    "FactoryRegistryReading",
    "FleetDefaultReading",
    "factory_registry_from_entry",
    "fleet_default_reading",
    "registry_path",
]

REGISTRY_KEY = "registry"
REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
DEFAULT_REGISTRY_PATH = "/etc/livespec/fabro-factories.json"

# The reserved `dispatcher.default_factory` value a repository commits to say
# "whichever factory the fleet currently defaults to", and the reserved
# top-level registry key that designates it. The second is reserved BOTH ways:
# because `default` names the designation, no factory may be named `default`.
FLEET_DEFAULT_FACTORY = "fleet"
REGISTRY_DEFAULT_KEY = "default"

_SERVER_KEY = "server"
_DOCKER_HOST_KEY = "docker_host"

# The committed address keys a registry-backed entry may not also carry. Each
# names an address the registry is the source of, so an entry declaring both
# has two answers and no rule for choosing between them.
_COMMITTED_ADDRESS_KEYS = (_SERVER_KEY, _DOCKER_HOST_KEY)

# "The key is not there", kept apart from every value it could hold. A registry
# that carries no `default` key has designated nothing, which is a different
# finding from one whose designation is unusable — the first is remedied by
# adding the key and the second by correcting it — and `None` cannot say which,
# because `"default": null` is a value an operator wrote.
_ABSENT = object()


@dataclass(frozen=True, kw_only=True)
class FactoryRegistryReading:
    """One factory entry's `registry` key and what the registry said, as read.

    `declared` answers whether the entry is registry-backed at all, and it is
    what every consumer branches on first: a reading of an ordinary `server`
    entry carries no registry facts and must not be graded as though it did.

    `path` is the registry file this reading actually READ, which is a
    configuration answer in its own right — the override and the host default
    are two different files and an operator fixing the wrong one changes
    nothing. It is carried on the reading rather than re-derived by the grade so
    the refusal names the file the resolution read and not the file a second
    environment lookup would have named.

    `server` and `detail` are mutually exclusive by construction and the pairing
    is the whole point: a resolved reading carries an address and no detail, an
    unresolvable one carries a detail and no address, and the grade refuses on
    the detail rather than on the address's absence — which is the state an
    ordinary serverless entry is also in.

    `docker_host` is the container-daemon address the selected entry declared,
    or None when it declared none. None here is an ANSWER rather than a fault —
    the sandbox-container sweep reports that factory's containers as unobserved,
    naming it — which is exactly why an entry whose `docker_host` is present and
    unusable is reported through `detail` instead: without that, a typo would be
    indistinguishable from a deliberate omission at every surface.

    `conflicting_keys` is the committed address keys the entry carried BESIDE
    `registry`, and it is kept apart from `detail` rather than folded into it
    because the two faults are in different files: this one is in the governed
    repository's own `.livespec.jsonc` and is fixed by a commit, while a detail
    is in host state and is fixed by the provisioning. A refusal that named the
    registry path for a conflict would point the operator at a file that had no
    part in the decision.

    `fleet` answers whether this factory was reached through the reserved
    `dispatcher.default_factory` value rather than through its own `registry`
    key, and it exists so a refusal can say WHICH committed line the operator
    should look at. The two have different remedies: a `"registry": true` entry
    that does not resolve is fixed by provisioning the entry the repository
    names, while an unresolvable fleet default is fixed by designating one at
    all, and a message naming `dispatcher.factories.fleet.registry` would point
    at a key no repository committed.

    `client` is the three client settings the SELECTED REGISTRY ENTRY declared.
    It is the registry side of the per-key merge `_factory_client_settings`
    performs, and it is empty on every reading that did not resolve an entry —
    a dispatch that is about to be refused supplies no client settings, which
    is what keeps a half-resolved registry from deciding how this Dispatcher
    speaks to a factory it could not address.
    """

    declared: bool = False
    fleet: bool = False
    path: str = ""
    server: str | None = None
    docker_host: str | None = None
    detail: str | None = None
    conflicting_keys: tuple[str, ...] = ()
    client: FactoryClientSettings = NO_FACTORY_CLIENT_SETTINGS


@dataclass(frozen=True, kw_only=True)
class FleetDefaultReading:
    """Which factory the registry designates as the fleet default, or why none.

    `path` is carried whichever way the reading went, because both answers are
    about a particular file and the refusal has to name the one that was read:
    the `LIVESPEC_FABRO_FACTORY_REGISTRY` override and the host default are
    different files, and an operator told only that no fleet default resolved
    has an even chance of designating one in the file this host does not read.

    `name` and `detail` are mutually exclusive by construction, and the pairing
    is what keeps an unresolvable designation from reading as an absent one: a
    repository that committed `fleet` has asked for a factory, so "the registry
    designates none" is a refusal rather than a fall-back to anything.
    """

    path: str
    name: str | None = None
    detail: str | None = None


# The reading every entry that is not registry-backed yields. A named constant
# rather than a bare `FactoryRegistryReading()` at each site so the absent
# answer has one identity a caller can compare against.
NO_FACTORY_REGISTRY = FactoryRegistryReading()


def registry_path() -> str:
    """The registry file this host reads: the override when usable, else the default.

    A SET-BUT-EMPTY override is treated as absent rather than as a path, because
    the empty string is not a file an operator meant to name and reading it would
    fail in the registry's own voice — an unresolvable registry naming `''`,
    whose remedy an operator cannot act on.
    """
    value = os.environ.get(REGISTRY_PATH_ENV_VAR)
    if value is not None and value != "":
        return value
    return DEFAULT_REGISTRY_PATH


def fleet_default_reading() -> FleetDefaultReading:
    """Which factory this host's registry designates as the fleet default.

    The RESERVED-KEY grade comes first, because a registry carrying a factory
    entry named `default` has overwritten the designation with a factory and
    there is no designation left to read: reporting it as a missing or
    malformed `default` value would send an operator to write one into the very
    key the mistake occupies. An object under that key is the discriminator —
    a designation is a string naming a factory, and a factory entry is an
    object — so no separate declaration is needed to tell the two apart.

    A name that resolves must also NAME an entry of this same file, which is
    the one grade that cannot be deferred to the per-entry reading: deferring it
    would refuse with "it holds no object entry named 'petri'", which reads as a
    missing factory when the fault is a designation pointing at nothing.
    """
    path = registry_path()
    table = _registry_table(path=path)
    if isinstance(table, str):
        return FleetDefaultReading(path=path, detail=table)
    declared = table.get(REGISTRY_DEFAULT_KEY, _ABSENT)
    if isinstance(declared, dict):
        return FleetDefaultReading(
            path=path,
            detail=(
                f"it carries a factory entry named {REGISTRY_DEFAULT_KEY!r}, which is"
                " the reserved fleet-default key and may not name a factory"
            ),
        )
    if declared is _ABSENT:
        return FleetDefaultReading(path=path, detail=f"it has no `{REGISTRY_DEFAULT_KEY}` key")
    name = _trimmed(value=declared)
    if name is None:
        return FleetDefaultReading(
            path=path,
            detail=(
                f"its `{REGISTRY_DEFAULT_KEY}` value {declared!r} is not a string"
                " non-empty after trimming"
            ),
        )
    if not isinstance(table.get(name), dict):
        return FleetDefaultReading(
            path=path,
            detail=(
                f"its `{REGISTRY_DEFAULT_KEY}` names {name!r}, which is no factory"
                " entry of its own"
            ),
        )
    return FleetDefaultReading(path=path, name=name)


def factory_registry_from_entry(
    *, entry: dict[str, Any], name: str, fleet: FleetDefaultReading | None = None
) -> FactoryRegistryReading:
    """Read what the registry says about ONE registry-backed factory.

    An entry that is not registry-backed and was not reached through `fleet`
    returns before the registry is looked at, so a repository that declares
    neither performs no filesystem read at all.

    A CONFLICTING entry returns before the read as well, and that ordering is
    deliberate: the dispatch is refused either way, so reading a file whose
    answer cannot be used would put a filesystem fault on the critical path of
    a refusal the committed configuration already earned — and would let the
    message report whichever fault it hit first.

    `fleet` is the designation reading when THIS name is the one the repository
    reaches through the reserved default, and `None` otherwise. Passing the
    reading rather than a flag is what lets an UNRESOLVABLE designation refuse
    in its own voice: the name it would have selected is exactly what is
    missing, so there is no entry to look up and the designation's own detail
    is the whole of what the operator needs.
    """
    if fleet is None and entry.get(REGISTRY_KEY) is not True:
        return NO_FACTORY_REGISTRY
    path = fleet.path if fleet is not None else registry_path()
    conflicting = tuple(key for key in _COMMITTED_ADDRESS_KEYS if key in entry)
    if conflicting:
        return FactoryRegistryReading(
            declared=True, fleet=fleet is not None, path=path, conflicting_keys=conflicting
        )
    if fleet is not None and fleet.detail is not None:
        return FactoryRegistryReading(declared=True, fleet=True, path=path, detail=fleet.detail)
    table = _registry_table(path=path)
    if isinstance(table, str):
        return FactoryRegistryReading(
            declared=True, fleet=fleet is not None, path=path, detail=table
        )
    return _entry_reading(table=table, path=path, name=name, fleet=fleet is not None)


def _entry_reading(
    *, table: dict[str, Any], path: str, name: str, fleet: bool
) -> FactoryRegistryReading:
    """One selected registry entry, resolved or refused, naming what was wrong."""
    selected = table.get(name)
    if not isinstance(selected, dict):
        return FactoryRegistryReading(
            declared=True,
            fleet=fleet,
            path=path,
            detail=f"it holds no object entry named {name!r}",
        )
    entry = cast("dict[str, Any]", selected)
    server = _trimmed(value=entry.get(_SERVER_KEY))
    if server is None:
        return FactoryRegistryReading(
            declared=True,
            fleet=fleet,
            path=path,
            detail=(
                f"its {name!r} entry gives no `server` string that is non-empty" " after trimming"
            ),
        )
    return _resolved_reading(entry=entry, path=path, name=name, server=server, fleet=fleet)


def _resolved_reading(
    *, entry: dict[str, Any], path: str, name: str, server: str, fleet: bool
) -> FactoryRegistryReading:
    """One entry whose server resolved, graded on its optional `docker_host`.

    MEMBERSHIP decides whether the key is graded at all, never truthiness. An
    ABSENT key is a complete answer — this factory declares no container-daemon
    address, which is what a committed entry carrying only a `server` already
    says and what makes the sweep report its containers as unobserved. A key the
    operator WROTE and that is not a usable address is refused like an invalid
    `server`, because falling back to the absent reading is indistinguishable
    from it at every surface: the sweep would report an unobserved factory for
    ever and name no fault.
    """
    client = factory_client_settings_from_entry(entry=entry)
    if _DOCKER_HOST_KEY not in entry:
        return FactoryRegistryReading(
            declared=True, fleet=fleet, path=path, server=server, client=client
        )
    docker_host = _trimmed(value=entry[_DOCKER_HOST_KEY])
    if docker_host is None:
        return FactoryRegistryReading(
            declared=True,
            fleet=fleet,
            path=path,
            detail=(
                f"its {name!r} entry gives a `docker_host` that is not a string"
                " non-empty after trimming"
            ),
        )
    return FactoryRegistryReading(
        declared=True,
        fleet=fleet,
        path=path,
        server=server,
        docker_host=docker_host,
        client=client,
    )


def _registry_table(*, path: str) -> dict[str, Any] | str:
    """The registry's top-level object, or WHY it could not be read.

    A reason rather than an exception or a None, because every caller of this is
    building a refusal an operator has to act on and the five faults have five
    different remedies — provision the file, make it readable, re-render it as
    text, fix the JSON, make the top level an object. `OSError` is named by TYPE
    rather than by its message so the reason stays stable across platforms while
    still saying which kind of unreadable it was.

    THE DECODE FAULT IS CAUGHT SEPARATELY AND IT IS NOT A STYLISTIC CHOICE.
    `UnicodeDecodeError` is a `ValueError`, not an `OSError`, so a registry whose
    bytes are not valid UTF-8 escaped this reading entirely and reached every
    consumer of the shared resolution as an exception: the per-factory survey,
    the plan liveness read, the merge-hold guard and the telemetry
    classification each died with a traceback, and the needs-human valve lane —
    whose absorbed-error set is `OSError` and the beads family — lost the whole
    valve list rather than one item's enrichment. The clause requires an
    unresolvable registry to be REPORTED on each of those surfaces, so no fault
    of this file may leave here as anything but a reason.

    It is reported apart from the JSON fault, which it would otherwise be
    collected by: the file DOES exist and IS readable, and its remedy is to
    re-render it rather than to correct its syntax. The exception's own message
    names the offending byte and its position, which is the one detail that
    makes an undecodable file findable, so it is carried through.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        return f"it is absent or unreadable ({type(error).__name__})"
    except UnicodeDecodeError as error:
        return f"its bytes are not valid UTF-8 text ({error})"
    try:
        parsed = cast("object", json.loads(text))
    except ValueError as error:
        return f"it does not parse as JSON ({error})"
    if not isinstance(parsed, dict):
        return "its top-level value is not an object"
    return cast("dict[str, Any]", parsed)


def _trimmed(*, value: object) -> str | None:
    """One registry value as a usable address, or None when it is not one.

    Trimmed rather than merely tested, because validity is judged after
    surrounding whitespace is removed and the TRIMMED text is what must travel:
    an address carrying a trailing newline passes every validity test and then
    reaches `fabro run --server` as an operand no engine resolves.
    """
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None
