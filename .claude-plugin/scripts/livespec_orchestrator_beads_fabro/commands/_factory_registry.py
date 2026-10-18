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
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__: list[str] = [
    "DEFAULT_REGISTRY_PATH",
    "NO_FACTORY_REGISTRY",
    "REGISTRY_KEY",
    "REGISTRY_PATH_ENV_VAR",
    "FactoryRegistryReading",
    "factory_registry_from_entry",
    "registry_path",
]

REGISTRY_KEY = "registry"
REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
DEFAULT_REGISTRY_PATH = "/etc/livespec/fabro-factories.json"

_SERVER_KEY = "server"
_DOCKER_HOST_KEY = "docker_host"

# The committed address keys a registry-backed entry may not also carry. Each
# names an address the registry is the source of, so an entry declaring both
# has two answers and no rule for choosing between them.
_COMMITTED_ADDRESS_KEYS = (_SERVER_KEY, _DOCKER_HOST_KEY)


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
    """

    declared: bool = False
    path: str = ""
    server: str | None = None
    docker_host: str | None = None
    detail: str | None = None
    conflicting_keys: tuple[str, ...] = ()


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


def factory_registry_from_entry(*, entry: dict[str, Any], name: str) -> FactoryRegistryReading:
    """Read what the registry says about ONE declared, registry-backed factory.

    An entry that is not registry-backed returns before the registry is looked
    at, so a repository that declares none performs no filesystem read at all.

    A CONFLICTING entry returns before the read as well, and that ordering is
    deliberate: the dispatch is refused either way, so reading a file whose
    answer cannot be used would put a filesystem fault on the critical path of
    a refusal the committed configuration already earned — and would let the
    message report whichever fault it hit first.
    """
    if entry.get(REGISTRY_KEY) is not True:
        return NO_FACTORY_REGISTRY
    path = registry_path()
    conflicting = tuple(key for key in _COMMITTED_ADDRESS_KEYS if key in entry)
    if conflicting:
        return FactoryRegistryReading(declared=True, path=path, conflicting_keys=conflicting)
    table = _registry_table(path=path)
    if isinstance(table, str):
        return FactoryRegistryReading(declared=True, path=path, detail=table)
    return _entry_reading(table=table, path=path, name=name)


def _entry_reading(*, table: dict[str, Any], path: str, name: str) -> FactoryRegistryReading:
    """One selected registry entry, resolved or refused, naming what was wrong."""
    selected = table.get(name)
    if not isinstance(selected, dict):
        return FactoryRegistryReading(
            declared=True,
            path=path,
            detail=f"it holds no object entry named {name!r}",
        )
    entry = cast("dict[str, Any]", selected)
    server = _trimmed(value=entry.get(_SERVER_KEY))
    if server is None:
        return FactoryRegistryReading(
            declared=True,
            path=path,
            detail=(
                f"its {name!r} entry gives no `server` string that is non-empty" " after trimming"
            ),
        )
    return _resolved_reading(entry=entry, path=path, name=name, server=server)


def _resolved_reading(
    *, entry: dict[str, Any], path: str, name: str, server: str
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
    if _DOCKER_HOST_KEY not in entry:
        return FactoryRegistryReading(declared=True, path=path, server=server)
    docker_host = _trimmed(value=entry[_DOCKER_HOST_KEY])
    if docker_host is None:
        return FactoryRegistryReading(
            declared=True,
            path=path,
            detail=(
                f"its {name!r} entry gives a `docker_host` that is not a string"
                " non-empty after trimming"
            ),
        )
    return FactoryRegistryReading(declared=True, path=path, server=server, docker_host=docker_host)


def _registry_table(*, path: str) -> dict[str, Any] | str:
    """The registry's top-level object, or WHY it could not be read.

    A reason rather than an exception or a None, because every caller of this is
    building a refusal an operator has to act on and the four faults have four
    different remedies — provision the file, make it readable, fix the JSON, make
    the top level an object. `OSError` is named by TYPE rather than by its
    message so the reason stays stable across platforms while still saying which
    kind of unreadable it was.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        return f"it is absent or unreadable ({type(error).__name__})"
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
