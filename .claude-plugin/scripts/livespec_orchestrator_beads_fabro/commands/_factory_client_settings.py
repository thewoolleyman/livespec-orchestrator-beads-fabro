"""The three CLIENT settings one factory entry declares, as read and as merged.

`bin`, `secret_channel` and `environment` say nothing about WHERE a factory is;
they say how this Dispatcher speaks to it. The host factory registry may carry
all three on a registry factory entry, with exactly the meaning each has on a
committed `dispatcher.factories` entry, and for a registry-backed factory each
is taken from the committed entry when the committed entry declares it and
otherwise from the registry entry. This module owns that reading and that merge
for both sides at once.

WHY ONE TYPE FOR BOTH SIDES RATHER THAN A COMMITTED ONE AND A REGISTRY ONE. The
merge is key by key, so the two sides must be comparable key by key, and two
types would have to agree about what "declares it" means for each of three keys
that spell it differently — a membership test for `bin` and `secret_channel`, a
nested `declared` flag for `environment`. Stated twice, the two statements drift
in the direction nothing announces: a registry value that silently loses to an
absent committed key reads exactly like a registry nobody consulted.

WHY MEMBERSHIP DECIDES, NEVER TRUTHINESS. An operator who wrote `"bin": null` or
`"secret_channel": ""` wrote something, and the validations downstream exist to
refuse it. Reading those as an absent key would hand the committed mistake the
registry's value instead of the refusal it has already earned — and the dispatch
would then run against a client nobody chose, with the committed file still
carrying the fault. `environment` carries its own `declared` flag for the same
reason, so this module reads that flag rather than re-deriving one.

WHY AN ENTRY THAT IS NOT REGISTRY-BACKED STILL PASSES THROUGH HERE. Its registry
side is the absent reading, so the merge returns exactly its committed values
and the pre-registry behaviour is preserved by construction rather than by a
branch. A branch would be a second code path for the ordinary case — the one
every adopter repository outside this fleet is on — and it would be exercised by
nothing in the fleet's own dispatches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._factory_environment import (
    FACTORY_ENVIRONMENT_KEY,
    NO_FACTORY_ENVIRONMENT,
    FactoryEnvironment,
    factory_environment_from_entry,
)

__all__: list[str] = [
    "FACTORY_BIN_KEY",
    "FACTORY_SECRET_CHANNEL_KEY",
    "NO_FACTORY_CLIENT_SETTINGS",
    "FactoryClientSettings",
    "effective_factory_client_settings",
    "factory_client_settings_from_entry",
]

FACTORY_BIN_KEY = "bin"
FACTORY_SECRET_CHANNEL_KEY = "secret_channel"  # noqa: S105 - a configuration KEY name


@dataclass(frozen=True, kw_only=True)
class FactoryClientSettings:
    """One factory entry's `bin`, `secret_channel` and `environment`, as read.

    Each key carries both WHETHER the entry declared it and WHAT it declared,
    because the merge below needs the first and the downstream validations need
    the second — and for two of the three the declared value may be unusable,
    which is a state the grade refuses rather than one this reading resolves.

    `secret_channel` is kept RAW rather than projected to `str | None`, because
    `_dispatcher_secret_channel` refuses an unrecognised transport by quoting
    what was written: a projection would collapse `null`, `""` and a misspelled
    transport onto the same absent answer, which selects the inline default and
    is the one outcome that silently persists a credential.

    `registry_sourced` names the keys whose EFFECTIVE value came from the
    registry entry rather than from the committed one, and it is empty on a bare
    READING of either side: a reading is of one source, so which source won is a
    fact about the MERGE and nothing else may claim to know it.

    It exists because each key's grade refuses by naming the key and a remedy,
    and the remedy differs by source — a committed `bin` is fixed by a commit to
    `.livespec.jsonc` and a registry `bin` by the fleet's provisioning. Without
    it every refusal a registry-supplied value reaches names a committed key the
    repository never wrote and prescribes removing it, which is a remedy the
    operator cannot perform; the clause requires the refusal to name the
    registry path as its source instead.
    """

    declares_bin: bool = False
    fabro_bin: str | None = None
    environment: FactoryEnvironment = NO_FACTORY_ENVIRONMENT
    declares_secret_channel: bool = False
    secret_channel: object = None
    registry_sourced: tuple[str, ...] = ()


# The reading an entry declaring none of the three yields, and the registry side
# of every entry that is not registry-backed. A named constant rather than a
# bare `FactoryClientSettings()` at each site so the absent answer has one
# identity a caller can compare against.
NO_FACTORY_CLIENT_SETTINGS = FactoryClientSettings()


def factory_client_settings_from_entry(*, entry: dict[str, Any]) -> FactoryClientSettings:
    """Read one factory entry's three client keys, committed or registry alike.

    The entry is read as a plain mapping, which is what lets the SAME reader
    serve a `dispatcher.factories` entry and a registry factory entry: the
    clause gives each key exactly the meaning it has on the committed entry, so
    two readers would be two accounts of one meaning.
    """
    return FactoryClientSettings(
        declares_bin=FACTORY_BIN_KEY in entry,
        fabro_bin=_optional_str(value=entry.get(FACTORY_BIN_KEY)),
        environment=factory_environment_from_entry(entry=entry),
        declares_secret_channel=FACTORY_SECRET_CHANNEL_KEY in entry,
        secret_channel=entry.get(FACTORY_SECRET_CHANNEL_KEY),
    )


def effective_factory_client_settings(
    *, entry: dict[str, Any], registry: FactoryClientSettings
) -> FactoryClientSettings:
    """What one factory's client settings ARE, from its two possible sources.

    ONE entry point rather than a reader the caller composes over a merger,
    because "what are this factory's client settings" is one question and a
    caller that answered it in two steps would be a second place the committed
    side is read — and reading the committed entry with a different rule from
    the one the merge assumes is how a key silently stops outranking the
    registry's.
    """
    return _merged(committed=factory_client_settings_from_entry(entry=entry), registry=registry)


def _merged(
    *, committed: FactoryClientSettings, registry: FactoryClientSettings
) -> FactoryClientSettings:
    """The committed value per key, else the registry's.

    Per KEY rather than per entry, which is the clause's own wording and is the
    difference that matters to an adopter: a repository pinning one factory's
    `bin` to an upgrade-candidate client keeps the registry's `secret_channel`
    and `environment` rather than having to restate them beside it.

    The SOURCE is recorded per key by the same rule and in the same place as the
    value, which is what keeps the two from disagreeing: a refusal naming the
    wrong source is a remedy pointed at a file whose correction changes nothing,
    and a source derived anywhere else would be a second account of a precedence
    that already lives here.
    """
    return FactoryClientSettings(
        declares_bin=committed.declares_bin or registry.declares_bin,
        fabro_bin=committed.fabro_bin if committed.declares_bin else registry.fabro_bin,
        environment=(
            committed.environment if committed.environment.declared else registry.environment
        ),
        declares_secret_channel=(
            committed.declares_secret_channel or registry.declares_secret_channel
        ),
        secret_channel=(
            committed.secret_channel
            if committed.declares_secret_channel
            else registry.secret_channel
        ),
        registry_sourced=_registry_sourced(committed=committed, registry=registry),
    )


def _registry_sourced(
    *, committed: FactoryClientSettings, registry: FactoryClientSettings
) -> tuple[str, ...]:
    """The keys the REGISTRY supplied: declared there and not in the committed entry.

    The test is `declared there AND not declared here` rather than a comparison
    of the two values, because the values legitimately coincide: a repository
    that commits the registry's own `bin` to pin it against a later inventory
    change has a COMMITTED value, and a refusal reading that equality as a
    registry source would send the operator to the provisioning for a key their
    own `.livespec.jsonc` decides.

    Membership is read through each key's own `declares_*` reading rather than
    through its value, for the reason the module docstring gives: `null` and
    `""` are values an operator wrote, and a truthiness test would report the
    registry as the source of a committed mistake it had no part in.
    """
    return tuple(
        key
        for key, declared_committed, declared_registry in (
            (FACTORY_BIN_KEY, committed.declares_bin, registry.declares_bin),
            (
                FACTORY_ENVIRONMENT_KEY,
                committed.environment.declared,
                registry.environment.declared,
            ),
            (
                FACTORY_SECRET_CHANNEL_KEY,
                committed.declares_secret_channel,
                registry.declares_secret_channel,
            ),
        )
        if declared_registry and not declared_committed
    )


def _optional_str(*, value: object) -> str | None:
    """One client value as a usable string, or None when it is not one."""
    return value if isinstance(value, str) and value != "" else None
