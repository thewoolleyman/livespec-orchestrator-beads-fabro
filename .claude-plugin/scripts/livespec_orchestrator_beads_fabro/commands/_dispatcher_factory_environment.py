"""The sandbox environment ONE factory declares, graded.

`_factory_environment` reads the `dispatcher.factories` entry's optional
`environment` key as WRITTEN; this module is the GRADE of that reading, and
the split is the pure-from-impure one used throughout this tree in its other
direction: the reading is a leaf `_config` imports, so a grade living beside
it could not reach `FactoryTarget` without closing an import cycle.

THE ID IS A PROJECTION, NOT A RE-READ. `factory_environment_id` answers off
the resolved target the dispatch preamble already stamped, for the same
resolve-once reason the integration contract and the ACP adapters are
projected rather than re-resolved: a second read of the same file cannot be
proven to agree with the first, and the disagreement would be invisible
because both reads produce a well-formed answer.

AN UNUSABLE DECLARATION IS REFUSED BEFORE THE CLAIM, for the reason the `bin`
refusal beside it is: the launch is where an unusable declaration would
otherwise surface, and by then the item has been admitted `ready -> active`
with an assignee. Worse than `bin`'s case, this one does not fail at the
launch at all — the id simply reduces to None, the flag is omitted, and the
run lands in the server's DEFAULT environment and dies in a prepare step with
no `mise` on PATH. That failure names nothing about the placement, so it is
read as the work-item's. The declaration has to be graded while the item is
still unclaimed, because there is no later surface at which the fault is
legible.

THE ENTRY IS GRADED AS A WHOLE, through `factory_declaration_refusal`, and
that composition lives here rather than beside either per-key grader. The
pre-dispatch config arm asks ONE question — does this repository's committed
`.livespec.jsonc` admit a dispatch at all — so it grades the resolved factory
ENTRY, not a ladder of key names that has to be extended in the dispatch
sequence every time an entry grows a key. `_dispatcher_factory_bin` cannot
host it: it is the older per-key module and importing this one from there
would put the composition below one of its own parts.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_bin_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_refusal,
    registry_sourced_path,
)
from livespec_orchestrator_beads_fabro.commands._factory_client_source import (
    client_key_source,
)
from livespec_orchestrator_beads_fabro.commands._factory_environment import (
    FACTORY_ENVIRONMENT_KEY,
)

__all__: list[str] = [
    "factory_declaration_refusal",
    "factory_environment_id",
    "factory_environment_refusal",
]


def factory_environment_id(*, factory: FactoryTarget) -> str | None:
    """The catalog environment id this factory's run intent must name.

    None means this factory names none, which is a complete answer: the run
    intent carries no environment of its own and the server selects whatever
    it selects today. It is ALSO what an unusable declaration reduces to,
    which is only safe because `factory_declaration_refusal` has already
    refused that dispatch before anything could read this.
    """
    return factory.environment.environment_id


def factory_environment_refusal(*, factory: FactoryTarget | None) -> str | None:
    """Refuse a declared `environment` that names no usable id, else None.

    An ABSENT key refuses nothing: it is the answer every entry that predates
    the key gives, and the one every factory on the pinned engine must keep
    giving. A DECLARED key that is not a non-empty string is refused rather
    than ignored, because ignoring it is indistinguishable from the absent
    case at every surface and lands the run in the server's default
    environment.

    `factory` is optional for the same reason the `bin` refusal's is: a caller
    that never ran the dispatch preamble — the needs-attention and standalone
    reconcile surfaces build their own arguments — has no target to consult,
    and that is the pre-key behaviour rather than a fault.

    The message NAMES THE SOURCE for the reason the `bin` refusal's does: a
    registry-supplied `environment` lands on this same reading, so a refusal
    naming only the committed key sends the operator to a line their
    `.livespec.jsonc` does not carry.
    """
    if factory is None or not factory.environment.declared:
        return None
    if factory.environment.environment_id is not None:
        return None
    source = client_key_source(
        factory=factory.name,
        key=FACTORY_ENVIRONMENT_KEY,
        registry_path=registry_sourced_path(factory=factory, key=FACTORY_ENVIRONMENT_KEY),
    )
    return (
        f"ERROR: factory {factory.name} declares"
        f" {source.name}{source.location}, which must be a"
        " non-empty string naming an environment in that factory's server"
        f" catalog; name one of factory {factory.name}'s catalog environments,"
        f" or remove {source.remedy} so the run intent carries none and that"
        " factory's server selects as it does today\n"
    )


def factory_declaration_refusal(*, factory: FactoryTarget | None) -> str | None:
    """Refuse the resolved factory ENTRY on the first unusable key, else None.

    The ONE grade the pre-dispatch config arm calls. The order is the order
    the keys were adopted in and nothing reads it: each refusal names its own
    key and its own remedy, so an entry carrying two faults is told about one
    of them and re-graded on the next invocation.
    """
    return (
        factory_bin_refusal(factory=factory)
        or factory_environment_refusal(factory=factory)
        or factory_registry_refusal(factory=factory)
    )
