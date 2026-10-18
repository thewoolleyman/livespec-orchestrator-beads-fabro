"""Finishing, from reconciliation, what a dead Dispatcher left a terminal run.

The absent-run release is this subsection's own recovery route. This is the
other half, and it adds NO route of its own: when the run is terminal and did
not succeed and no live owner is established, the Dispatcher applies the
disposition its OWN terminal handling assigns to that run's recorded outcome,
exactly as if the owning Dispatcher had observed it. So every decision here is
delegated — to the provider-limit release, the first-stall release, the
non-convergence bounce, and the `blocked / needs-human` rest with its cause
comment — and nothing in this module decides what any of them means.

THE OUTCOME IS BUILT THROUGH THE DISPATCH PATH'S OWN MAPPER, not re-derived.
`fabro_run_terminal_outcome` is where "which terminal is this" lives, and it
needs a `DispatchPlan`; so a plan is resolved here the same way the
`reconcile-merged` valve resolves one, from the target's own committed
declaration, because a reconciliation that resolved its own contract could
dispose an item by rules the original dispatch never ran under.

A STALL CANCELLATION IS READ OFF THE JOURNAL AND NEVER OFF THE RUN. The
watchdog's own disposition keys on a terminal status (`stalled-no-progress`)
the Dispatcher STAMPS after it cancels — no `fabro inspect` payload carries
it, because to the factory the run was simply removed. The cancel site
journals one row per cancellation naming the item and the run, and that row is
the only honest evidence this was a watchdog cancel rather than an ordinary
failure. Without it the first-stall release could not be completed at all, and
the item would rest for a human on a cancellation the clause releases.

EVIDENCE IS OBSERVED BEFORE ANYTHING IS GRADED, which is why this module
exposes the reading and the application as two functions. The ladder holds a
failed run whose failure evidence cannot be read as
`terminal-evidence-unavailable`, so the read has to happen before the grade;
the application happens inside the recovery, after its precondition re-read.
One function doing both would either grade after acting or act before the
re-read.

THE FINAL ARM IS THE CLAUSE'S OWN REQUIREMENT, not an invention: a failure no
release route claims rests at `blocked / needs-human` with its cause comment,
because a run nobody is left to observe would otherwise sit `active` forever —
the exact state this whole subsection exists to end. It is decided by
RE-READING the row rather than by predicting which route fired: every route is
fail-soft, so a route can decline or can fail its own ledger write, and only
the row itself says what happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_claim import claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
    inspect_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_repo_config import livespec_config_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_telemetry import STALL_STATUS
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "EFFECT_NEEDS_HUMAN_REST",
    "EFFECT_TERMINAL_ROUTING",
    "TerminalObservation",
    "TerminalReadContext",
    "apply_terminal_disposition",
    "observe_terminal_outcome",
]

# The two effects this module performs, named so a recovery record can say
# which ones THIS pass took. The routing is always applied; the rest is taken
# only when no release route claimed the item.
EFFECT_TERMINAL_ROUTING = "terminal-routing"
EFFECT_NEEDS_HUMAN_REST = "needs-human-rest"

_ACTIVE_STATUS = "active"
_FABRO_ASSIGNEE = "fabro"
_BLOCKED_STATUS = "blocked"
_RUN_ID_KEY = "run_id"
_WORK_ITEM_KEY = "work_item_id"
_STAGE_KEY = "stage"

_LEDGER_READ_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


@dataclass(frozen=True, kw_only=True)
class TerminalReadContext:
    """Everything reading ONE run's terminal record needs, besides the run.

    A carrier rather than seven parameters, and the grouping is the reading's
    own: `repo` and `fabro_bin` resolve the plan the mapper needs, the factory
    pair names WHICH server is asked, `runner` and `journal` are the two seams
    the read goes through, and `records` is the already-taken journal reading
    the watchdog evidence comes from. None of them varies per claim within one
    factory's survey.
    """

    repo: Path
    journal: JournalFile
    runner: CommandRunner
    records: tuple[Mapping[str, object], ...]
    fabro_bin: str
    factory_name: str
    factory_server_url: str | None


@dataclass(frozen=True, kw_only=True)
class TerminalObservation:
    """One run's recorded terminal outcome, as this pass read it.

    A carrier rather than the bare `DispatchOutcome` so a caller cannot
    confuse "this run is terminal and here is its outcome" with an outcome the
    caller built itself: only an observation taken through
    `observe_terminal_outcome` has been read off the factory's own record,
    which is what the disposition is entitled to act on.
    """

    outcome: DispatchOutcome


def observe_terminal_outcome(
    *,
    context: TerminalReadContext,
    work_item_id: str,
    run_id: str,
) -> TerminalObservation | None:
    """This run's recorded terminal outcome, or None when it cannot be read.

    `None` is the `terminal-evidence-unavailable` reading and never a verdict:
    an unreadable record says nothing about whether the run failed for a cause
    any release route claims, so it must not be released and must not be
    converted into a needs-human decision.
    """
    plan = _terminal_plan(
        repo=context.repo,
        work_item_id=work_item_id,
        fabro_bin=context.fabro_bin,
        factory_name=context.factory_name,
        factory_server_url=context.factory_server_url,
    )
    inspect = inspect_run(plan=plan, runner=context.runner, journal=context.journal, run_id=run_id)
    if not _evidence_readable(inspect=inspect):
        return None
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        # A non-zero client exit stands for the dead Dispatcher's own client,
        # which is gone. The run is already known terminal-and-not-succeeded
        # from the factory listing, so a zero here would make the mapper read
        # it as an ordinary pull-request reconciliation and return no outcome.
        exit_code=1,
        stderr="",
    )
    if outcome is None:
        return None
    if _watchdog_cancelled(records=context.records, work_item_id=work_item_id, run_id=run_id):
        return TerminalObservation(outcome=replace(outcome, status=STALL_STATUS))
    return TerminalObservation(outcome=outcome)


def apply_terminal_disposition(
    *,
    repo: Path,
    item: WorkItem,
    observation: TerminalObservation,
    journal: JournalFile,
    now_iso: str,
) -> tuple[str, ...]:
    """Apply the Dispatcher's own disposition for this terminal, then rest it.

    The order mirrors `post_run_dispositions` exactly: the human-gate
    escalation and its cause record first, then the three non-green routes as
    one group, then the rest for a failure none of them claimed.
    """
    outcome = observation.outcome
    if outcome.status == _BLOCKED_STATUS:
        escalate_needs_human_block(repo=repo, item=item, outcome=outcome, journal=journal)
        record_needs_human_cause(repo=repo, item=item, outcome=outcome, journal=journal)
    dispose_terminal_routing(
        repo=repo, item=item, outcome=outcome, journal=journal, now_iso=now_iso
    )
    if not _still_claimed(repo=repo, work_item_id=item.id):
        return (EFFECT_TERMINAL_ROUTING,)
    rest = replace(outcome, status=_BLOCKED_STATUS, needs_human_kind=STAGE_FAILURE)
    escalate_needs_human_block(repo=repo, item=item, outcome=rest, journal=journal)
    record_needs_human_cause(repo=repo, item=item, outcome=rest, journal=journal)
    return (EFFECT_TERMINAL_ROUTING, EFFECT_NEEDS_HUMAN_REST)


def _evidence_readable(*, inspect: FabroInspectResult | None) -> bool:
    """Whether this run's record carries failure evidence that can be READ.

    Three separate failures to measure, and each one is `unavailable` rather
    than a verdict. A client that did not run or exited non-zero asked nothing.
    Output the payload reader could not parse answered with text nobody can
    grade — and that case is the one most easily mistaken for an answer,
    because the mapper WILL build a plain `failed` outcome from an empty
    payload and the item would then rest for a human on no evidence at all. A
    record carrying no failure block has nothing for a release route to
    classify, which is the clause's "failure evidence that is missing".
    """
    if inspect is None or inspect.command.exit_code != 0:
        return False
    return inspect.payload is not None and inspect.failure is not None


def _still_claimed(*, repo: Path, work_item_id: str) -> bool:
    """Whether the row is STILL `active` under the `fabro` claim.

    An unreadable row answers `False`, which WITHHOLDS the needs-human rest
    rather than applying it: resting an item whose state could not be read
    would overwrite a disposition that may already have landed, and the next
    pass observes the claim again.
    """
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=work_item_id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(row, AttemptFailure):
        return False
    return row.status == _ACTIVE_STATUS and row.assignee == _FABRO_ASSIGNEE


def _watchdog_cancelled(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
    run_id: str,
) -> bool:
    return any(
        record.get(_STAGE_KEY) == STALL_CANCEL_STAGE
        and record.get(_WORK_ITEM_KEY) == work_item_id
        and record.get(_RUN_ID_KEY) == run_id
        for record in records
    )


def _terminal_plan(
    *,
    repo: Path,
    work_item_id: str,
    fabro_bin: str,
    factory_name: str,
    factory_server_url: str | None,
) -> DispatchPlan:
    """The plan subset the terminal mapper needs, resolved as a dispatch would.

    The janitor is deliberately absent and the two file paths are nominal: no
    node runs here, and the mapper reads only the item, the factory target and
    the resolved integration contract. The DEFAULT BRANCH is left unresolved
    rather than probed, because resolving it costs a git round trip per claim
    and no reading this mapper takes consults it.
    """
    return build_plan(
        repo=repo,
        work_item_id=work_item_id,
        workflow_toml=repo / "tmp" / f"stranded-claim-{work_item_id}-workflow.toml",
        goal_file=repo / "tmp" / f"stranded-claim-{work_item_id}-goal.md",
        fabro_bin=fabro_bin,
        fabro_factory_name=factory_name,
        fabro_factory_server=factory_server_url,
        janitor=None,
        janitor_checkout=repo / "tmp" / f"stranded-claim-{work_item_id}-janitor",
        config_text=livespec_config_text(repo=repo),
    )
