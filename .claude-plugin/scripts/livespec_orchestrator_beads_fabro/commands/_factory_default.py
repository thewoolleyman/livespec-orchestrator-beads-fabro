"""Which `dispatcher.factories` entry is the CONFIGURED default, env excluded.

Split out of `_config` for the same reason `_factory_registry` and
`_factory_environment` are: it is one question about the dispatcher block with
one answer, and it now has a SECOND reader. `_config.resolve_fabro_factory` asks
it after its own two environment-and-argument layers have declined;
`_dispatcher_overflow_factories` asks it with no layers at all, because the
committed `overflow_factories` array is graded against the committed default and
against nothing a shell exported.

THAT SECOND READER IS WHY THE DERIVATION IS HERE RATHER THAN RESTATED. Reaching
for `resolve_fabro_factory` to answer "what is the default" looks right and is
wrong in both directions at once: it reads `LIVESPEC_FABRO_FACTORY` FIRST, so an
operator who exported the overflow factory's name would see the array that names
the committed default admitted — the one shape the clause forbids — and would
then see the candidate list open with the overflow factory, where a utilization
tie makes it win. Restating the derivation in the second reader would be two
authorities on one answer, and the disagreement would be invisible because both
readings produce a declared factory name.

WHY AN UNDECLARED `default_factory` FALLS BACK TO THE IMPLICIT TARGET RATHER
THAN TO THE SOLE DECLARED ENTRY. `"default"` is the implicit single-factory
target an unconfigured repository resolves, which is how the bare CLI's ambient
behaviour is preserved; a repository that declares `factories` without naming a
default has named no default, and inferring one from "there is only one entry"
would make the answer change the moment a second entry is declared.

WHY THE RESERVED `fleet` VALUE IS GRADED FIRST AND NOT AGAINST THE COMMITTED
TABLE. The whole point of committing `fleet` is that the factory it selects is
one the repository need not declare — "a factory reached through the fleet
default that the repository's `dispatcher.factories` does not declare MUST be
treated as a registry-backed entry of that name" — so putting the existing
"names a declared entry" test in front of it would send every fleet repository
to the implicit target, i.e. to whichever Fabro the dispatching host runs, with
no error at all. The value is reserved precisely so that no committed table can
be consulted about it.

WHY AN UNRESOLVABLE DESIGNATION KEEPS THE RESERVED VALUE AS THE NAME. The
alternative is the implicit target, and that is the one answer a repository
committing `fleet` must never receive: it resolves to a target with no server,
which every downstream surface reads as the ambient local Fabro, so the dispatch
would succeed on the wrong machine with its own record naming a factory the work
never reached. Returning the reserved value instead carries the unresolvable
state forward to `_dispatcher_factory_registry`, where it is refused before the
claim.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._factory_registry import (
    FLEET_DEFAULT_FACTORY,
    FleetDefaultReading,
    fleet_default_reading,
)

__all__: list[str] = [
    "IMPLICIT_FACTORY_NAME",
    "configured_factory_name",
    "fleet_selection",
]

# The implicit single-factory target. It carries no server value, so every
# downstream caller keeps today's ambient Fabro CLI behaviour on it.
IMPLICIT_FACTORY_NAME = "default"

_DEFAULT_FACTORY_KEY = "default_factory"
_FACTORIES_KEY = "factories"


def configured_factory_name(*, block: dict[str, Any]) -> str:
    """The configured default factory's name, or the implicit target's.

    `dispatcher.default_factory` wins only when it NAMES a declared
    `dispatcher.factories` entry: a name that matches no entry would resolve to a
    target with no server, which every downstream surface reads as the ambient
    local Fabro — so the implicit target is returned under its own name instead
    of under a declared-looking one that resolves to nothing.
    """
    declared = block.get(_DEFAULT_FACTORY_KEY)
    factories_raw = block.get(_FACTORIES_KEY)
    if declared == FLEET_DEFAULT_FACTORY:
        return fleet_default_reading().name or FLEET_DEFAULT_FACTORY
    if not isinstance(declared, str) or declared == "":
        return IMPLICIT_FACTORY_NAME
    if not isinstance(factories_raw, dict):
        return IMPLICIT_FACTORY_NAME
    if declared not in cast("dict[str, Any]", factories_raw):
        return IMPLICIT_FACTORY_NAME
    return declared


def fleet_selection(*, block: dict[str, Any], name: str) -> FleetDefaultReading | None:
    """The designation reading when `name` is reached through `fleet`; else None.

    Asked PER NAME rather than once per repository, because a fleet repository
    still selects other factories: an explicit `--factory legacy` names a
    committed entry that the registry has nothing to say about, and handing it a
    designation reading would make it registry-backed and refuse it over a
    registry key it never declared.

    The unresolved designation is matched against the RESERVED VALUE, which is
    the name `configured_factory_name` carries forward when nothing resolved.
    Without that arm the refusal would be lost: the reading would come back
    `None`, the target would carry no registry facts, and the dispatch would
    proceed to a factory literally named `fleet` with no server — the ambient
    local engine, silently.
    """
    if block.get(_DEFAULT_FACTORY_KEY) != FLEET_DEFAULT_FACTORY:
        return None
    reading = fleet_default_reading()
    if reading.name == name or (reading.name is None and name == FLEET_DEFAULT_FACTORY):
        return reading
    return None
