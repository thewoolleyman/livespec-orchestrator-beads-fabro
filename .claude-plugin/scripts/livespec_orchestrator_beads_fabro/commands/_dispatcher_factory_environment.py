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
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget

__all__: list[str] = [
    "factory_environment_id",
]


def factory_environment_id(*, factory: FactoryTarget) -> str | None:
    """The catalog environment id this factory's run intent must name.

    None means this factory names none, which is a complete answer: the run
    intent carries no environment of its own and the server selects whatever
    it selects today.
    """
    return factory.environment.environment_id
