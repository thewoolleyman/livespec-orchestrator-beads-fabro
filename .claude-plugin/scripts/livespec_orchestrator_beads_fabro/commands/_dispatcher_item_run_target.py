"""The factory ONE item's dispatch went to, and the bound on reading its events.

`SPECIFICATION/contracts.md` says Fabro capability "is read from the dispatch's
resolved factory server, never a local binary", and the repository-level trap is
catalogued in `AGENTS.md`: a bare `fabro` invocation answers for `127.0.0.1` and
reports `No running processes found` while the dispatch is perfectly healthy on
`hp`. So the factory is resolved from the work-item's own recorded
`dispatch_factory` stamp first, falling back to the repository's configured
default, and a factory declaring no server url is treated as UNRESOLVED rather
than surveyed through whatever the client would have defaulted to.

THE RESOLUTION NEVER FAILS ITS CALLER. Its callers run AFTER the work they
follow has already happened, so an unreachable tenant or an unreadable
`.livespec.jsonc` must degrade the answer to `None` rather than raise through a
caller that has already finished its work — the same reasoning
`_dispatcher_run_reconcile_hook` gives for its own hook. `None` is the word for
"no factory resolves", which is a fact about configuration and never an
exception the caller has to absorb.

BOTH NAMES LIVED IN THE RETIRED EVENT PROJECTION, and neither belonged to it.
v127 removed the `agent.acp.failover` projection that declared them, while the
per-attempt cost read it left standing asks the same two questions: which
factory holds this item's run, and how long may one `fabro events` call take.
They are here, in a leaf of their own, so a later retirement of some other
consumer cannot take the cost path's bound with it — a removal whose only
symptom is an unbounded subprocess against a slow factory.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import dispatch_factory_for

__all__: list[str] = [
    "ACP_EVENTS_TIMEOUT_SECONDS",
    "resolve_item_run_factory",
]

# The events read is a single short JSON fetch against an already-reachable
# factory, so it is bounded well below the `ps` survey's minute: a slow answer
# here is better reported as an undetermined cost than waited on while a
# terminal dispatch holds its caller open.
ACP_EVENTS_TIMEOUT_SECONDS = 30.0

# The same absorbed set the lifecycle reconcile hook enumerates: an unreachable
# tenant or an unreadable `.livespec.jsonc` must degrade the factory
# resolution, never raise through a caller that has already finished its work.
_RECOVERABLE: tuple[type[Exception], ...] = (
    OSError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def resolve_item_run_factory(*, repo: Path, work_item_id: str) -> FactoryTarget | None:
    """The factory THIS item's dispatch went to, or `None` when none resolves.

    The item's recorded stamp wins over the repository default for the reason
    `targeted_factories` gives: an item dispatched to `vps` must not have its
    run looked for on `hp`, where the clean answer is a run that does not exist.
    """
    stamped = attempt(
        action=lambda: dispatch_factory_for(
            path=store_config(repo=repo), work_item_id=work_item_id
        ),
        exceptions=_RECOVERABLE,
    )
    factory = attempt(
        action=lambda: resolve_fabro_factory(
            cwd=repo, factory=None if isinstance(stamped, AttemptFailure) else stamped
        ),
        exceptions=_RECOVERABLE,
    )
    if isinstance(factory, AttemptFailure) or factory.server is None:
        return None
    return factory
