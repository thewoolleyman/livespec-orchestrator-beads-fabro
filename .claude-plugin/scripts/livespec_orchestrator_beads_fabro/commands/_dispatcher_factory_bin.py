"""The engine client binary ONE factory declares, resolved against the global.

`LIVESPEC_FABRO_BIN`, `dispatcher.fabro_bin` and the home-path probe answer
one question for the whole Dispatcher — which `fabro` client drives a run —
and a single global answer was correct while every declared factory ran the
same engine. Running an upgrade candidate beside the production server breaks
that in both directions: the candidate client cannot talk to the legacy
server and the legacy client cannot talk to the candidate, so the client is a
property OF THE FACTORY rather than of the host.

A factory entry's optional `bin` key carries it, and this module is the one
place the two layers meet. An ABSENT key is a complete answer — this factory
runs whatever the host resolves — so it returns the fallback untouched rather
than probing anything of its own, which is what keeps every repository that
declares no `bin` on exactly the resolution it had before the key existed.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget

__all__: list[str] = [
    "factory_fabro_bin",
]


def factory_fabro_bin(*, factory: FactoryTarget | None, fallback: str) -> str:
    """The engine client binary driving Fabro calls against `factory`.

    `fallback` is the GLOBAL resolution the caller already has in hand, passed
    in rather than resolved here: this module answers what the factory says,
    and a second global resolution taken at this depth could not be proven to
    agree with the one the dispatch record and the plan already carry.

    `factory` is optional because a caller that never ran the dispatch
    preamble — the needs-attention and standalone reconcile surfaces construct
    their own arguments — has no target to consult, and that is the
    pre-factory behaviour rather than a fault.
    """
    _ = factory
    return fallback
