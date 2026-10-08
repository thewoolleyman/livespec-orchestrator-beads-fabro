"""Fetching ONE run's events from the dispatch's resolved factory, and projecting.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The Dispatcher MUST fetch events from the run's resolved
factory target, project by stable event id, calculate holds from
occurrence time, and replay projection during reconciliation."

THE FACTORY IS THE DISPATCH'S OWN, NEVER A DEFAULT AND NEVER LOCAL. The
same section says Fabro capability "is read from the dispatch's resolved
factory server, never a local binary", and the repository-level trap is
already catalogued in `AGENTS.md`: a bare `fabro` invocation answers for
`127.0.0.1` and reports `No running processes found` while the dispatch
is perfectly healthy on `hp`. So the factory is resolved from the
work-item's own recorded `dispatch_factory` stamp first, falling back to
the repository's configured default, and a factory declaring no server
url is treated as an UNREAD stream rather than surveyed through whatever
the client would have defaulted to.

A PROJECTION NEVER FAILS ITS CALLER. Both entry points run AFTER the work
they follow has already happened -- a terminal dispatch outcome, or a
reconciliation pass -- so an unreachable factory is a fact about the
factory, exactly as `_dispatcher_run_reconcile_hook` argues for its own
hook. What an unreadable stream produces is the projection-failure fact,
which is loud, durable, and stops unattended picking; what it must never
produce is an exception that loses the outcome the caller was reporting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_event_projection import (
    AcpProjectionResult,
    AcpProjectionTarget,
    classify_events_failure,
    project_fetched_events,
    record_projection_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import REASON_FETCH_FAILED
from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_primary_generations,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
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
    "AcpProjectionRequest",
    "ProjectionJournal",
    "project_run_events",
    "resolve_projection_factory",
]

# The events read is a single short JSON fetch against an already-reachable
# factory, so it is bounded well below the `ps` survey's minute: a slow
# answer here is better reported as a timed-out projection fact than waited
# on while a terminal dispatch holds its caller open.
ACP_EVENTS_TIMEOUT_SECONDS = 30.0

_UNRESOLVED_FACTORY = "unresolved"

# The same absorbed set the lifecycle reconcile hook enumerates: an
# unreachable tenant or an unreadable `.livespec.jsonc` must degrade the
# factory resolution, never raise through a caller that has already
# finished its work.
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


class ProjectionJournal(Protocol):
    """The one-method append seam every projection writer is handed.

    Public because both call sites hand in their own value -- the
    dispatcher a `JournalFile`, a read-only lane the reconciler's
    `InertJournal` -- and a private protocol could not name that shared
    expectation across the module boundary.
    """

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class AcpProjectionRequest:
    """One run to project, and the repository context it belongs to."""

    repo: Path
    repo_name: str
    work_item_id: str
    run_id: str
    journal_path: Path | None
    # Whether the dispatch this run belongs to reached a GREEN terminal. It is
    # the only evidence available here that a node's primary attempt actually
    # completed successfully, and it is carried as the run's own verdict rather
    # than as a node set so no caller can assert a node succeeded that the
    # dispatch never reported on.
    run_succeeded: bool = False


def resolve_projection_factory(*, repo: Path, work_item_id: str) -> FactoryTarget | None:
    """The factory THIS item's dispatch went to, or `None` when none resolves.

    The item's recorded stamp wins over the repository default for the
    reason `targeted_factories` gives: an item dispatched to `vps` must
    not have its events looked for on `hp`, where the clean answer is a
    run that does not exist.
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


def project_run_events(
    *,
    request: AcpProjectionRequest,
    journal: ProjectionJournal,
    runner: CommandRunner | None = None,
    factory: FactoryTarget | None = None,
) -> AcpProjectionResult:
    """Read one run's events from its resolved factory and project them.

    A repository with no fallback-enabled node returns the empty result
    before any factory is resolved or any process is launched, which is
    the additive guarantee this feature opens with: the v107 path pays
    nothing for a projection that could have nothing to project.

    `factory` is supplied by the reconciler, which is ALREADY iterating
    one declared factory at a time and has surveyed that factory's
    inventory through its own target. Re-resolving here would let a
    replay read events from the repository default while the run it is
    replaying lives on another host -- the wrong-population trap, arriving
    through a default rather than through a typo. Every other caller
    leaves it None and gets the item's own recorded stamp.
    """
    generations = resolve_acp_primary_generations(repo=request.repo)
    if not generations:
        return AcpProjectionResult()
    succeeded: frozenset[str] = frozenset(generations) if request.run_succeeded else frozenset()
    if factory is None:
        factory = resolve_projection_factory(repo=request.repo, work_item_id=request.work_item_id)
    if factory is None or factory.server is None:
        return record_projection_failure(
            target=_target(
                request=request,
                generations=generations,
                succeeded=succeeded,
                factory_name=_UNRESOLVED_FACTORY,
                factory_server_url=_UNRESOLVED_FACTORY,
            ),
            reason=REASON_FETCH_FAILED,
            exit_code=None,
            journal=journal,
        )
    return _fetch_and_project(
        request=request,
        target=_target(
            request=request,
            generations=generations,
            succeeded=succeeded,
            factory_name=factory.name,
            factory_server_url=factory.server,
        ),
        factory=factory,
        journal=journal,
        runner=runner,
    )


def _target(
    *,
    request: AcpProjectionRequest,
    generations: Mapping[str, str],
    succeeded: frozenset[str],
    factory_name: str,
    factory_server_url: str,
) -> AcpProjectionTarget:
    """The projection target one request and one resolved factory describe."""
    return AcpProjectionTarget(
        repo_name=request.repo_name,
        run_id=request.run_id,
        work_item_id=request.work_item_id,
        factory_name=factory_name,
        factory_server_url=factory_server_url,
        primary_generations=generations,
        succeeded_nodes=succeeded,
    )


def _fetch_and_project(
    *,
    request: AcpProjectionRequest,
    target: AcpProjectionTarget,
    factory: FactoryTarget,
    journal: ProjectionJournal,
    runner: CommandRunner | None,
) -> AcpProjectionResult:
    """Shell the server-qualified events read, then route what came back.

    The whole `factory` rides in rather than its server url and dev token
    alone, because the client binary is a third property of the same target:
    reading a candidate-engine run's events through the legacy client returns
    an unusable payload that is indistinguishable from a run with nothing to
    project.
    """
    port = FabroPort(
        fabro_bin=factory_fabro_bin(factory=factory, fallback=resolve_fabro_bin(cwd=request.repo)),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=ShellCommandRunner() if runner is None else runner,
        cwd=request.repo,
    )
    events = port.events(run_id=request.run_id, timeout_seconds=ACP_EVENTS_TIMEOUT_SECONDS)
    reason = classify_events_failure(
        exit_code=events.command.exit_code,
        output=f"{events.command.stdout}\n{events.command.stderr}",
        payload=events.payload,
    )
    if reason is not None:
        return record_projection_failure(
            target=target,
            reason=reason,
            exit_code=events.command.exit_code,
            journal=journal,
        )
    return project_fetched_events(
        target=target,
        payload=events.payload,
        journal=journal,
        journal_path=request.journal_path,
    )
