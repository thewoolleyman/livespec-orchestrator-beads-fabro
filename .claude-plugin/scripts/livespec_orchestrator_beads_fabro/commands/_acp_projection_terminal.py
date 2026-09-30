"""Projecting a run's ACP fallback events once its dispatch reaches a terminal.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": a hold "may come from ... an idempotently projected
`agent.acp.failover` event from a run of ANY eventual outcome", and the
model-fallback warning stands because "Later run failure does not erase
it".

SO THIS FIRES ON EVERY TERMINAL, NOT ONLY ON GREEN. A run that fell back
at `implement` and then failed at `review` observed a real outage, and
the next dispatch must skip the candidate that caused it. Gating the
projection on success would lose exactly the evidence that matters most
-- the runs that went badly -- and would lose it silently, because a
repository with no holds looks identical to one whose holds were never
projected.

THE RUN'S VERDICT IS STILL CARRIED, for the other half of the lifecycle:
only a GREEN terminal can evidence that a node's primary attempt
"completed successfully", which is what clears a warning. A non-green
terminal projects the holds and warnings and clears nothing, which is
the conservative direction -- a warning that stands costs an operator a
row to read, while one cleared on no evidence costs them the knowledge
that their primary is broken.

IT NEVER RAISES AT ITS CALLER. `post_run_dispositions` is reporting a
terminal that has already happened; an unreachable factory is a fact
about the factory, and the durable record of it is the
projection-failure fact, not a traceback that loses the outcome.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_event_projection import AcpProjectionResult
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    AcpProjectionRequest,
    ProjectionJournal,
    project_run_events,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "PROJECTION_ERROR_STAGE",
    "project_terminal_run_events",
]

PROJECTION_ERROR_STAGE = "acp-projection-hook-error"

_GREEN_STATUS = "green"
_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")

# A bug in the projection is NOT in this tuple and still raises: "never
# fail the caller" is a promise about the factory and the filesystem, not
# a licence to swallow our own defects. Same enumeration, and the same
# reasoning, as `_dispatcher_run_reconcile_hook._HOOK_ERRORS`.
_HOOK_ERRORS: tuple[type[Exception], ...] = (OSError, RuntimeError, ValueError)


class _TerminalOutcome(Protocol):
    @property
    def work_item_id(self) -> str:
        """Ledger id the terminal outcome belongs to."""
        ...

    @property
    def status(self) -> str:
        """The dispatch's terminal verdict."""
        ...

    @property
    def fabro_run_id(self) -> str | None:
        """The Fabro run this dispatch created, when one was created."""
        ...


def project_terminal_run_events(
    *,
    outcome: _TerminalOutcome,
    repo: Path,
    journal: ProjectionJournal,
    runner: CommandRunner | None = None,
) -> AcpProjectionResult:
    """Project one terminal dispatch's run, absorbing any failure to do so.

    A terminal that created NO run has no event stream and no fact to
    raise: the failure fact says "this run's events were not read", and
    minting one for a run that never existed would stop the unattended
    drain on a dispatch that never reached a factory at all.
    """
    run_id = outcome.fabro_run_id
    if run_id is None:
        return AcpProjectionResult()
    projected = attempt(
        action=lambda: project_run_events(
            request=AcpProjectionRequest(
                repo=repo,
                repo_name=repo.name,
                work_item_id=outcome.work_item_id,
                run_id=run_id,
                journal_path=repo.joinpath(*_JOURNAL_SUBPATH),
                run_succeeded=outcome.status == _GREEN_STATUS,
            ),
            journal=journal,
            runner=runner,
        ),
        exceptions=_HOOK_ERRORS,
    )
    if isinstance(projected, AttemptFailure):
        journal.append(
            record={
                "stage": PROJECTION_ERROR_STAGE,
                "work_item_id": outcome.work_item_id,
                "fabro_run_id": run_id,
                "reason": type(projected.error).__name__,
            }
        )
        return AcpProjectionResult()
    return projected
