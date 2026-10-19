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
"""

from __future__ import annotations

from typing import Any, cast

__all__: list[str] = [
    "IMPLICIT_FACTORY_NAME",
    "configured_factory_name",
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
    if not isinstance(declared, str) or declared == "":
        return IMPLICIT_FACTORY_NAME
    if not isinstance(factories_raw, dict):
        return IMPLICIT_FACTORY_NAME
    if declared not in cast("dict[str, Any]", factories_raw):
        return IMPLICIT_FACTORY_NAME
    return declared
