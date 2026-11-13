"""The two boundaries at which one dispatch's cycle observations are evaluated.

Plan slice S6 (`bd-ib-z2y4ca`). `SPECIFICATION/contracts.md` says the workflow
"MUST evaluate the retained cycle observations at its pre-merge convergence
verification boundary and when recording a terminal non-converged run; immediate
evaluation after each cycle is not required". This module is both of those
positions, and ONE evaluation serves them: the two readings differ in WHEN they
are taken and in nothing else, which is what keeps them from measuring
differently.

THE PRE-MERGE POSITION IS THE DISPATCHER'S OWN. It is the moment the pull
request has been confirmed and nothing about merging has been decided yet — the
same instant the branch-versus-base size is recorded — so a breach found there
can still stop the merge. A breach after the merge could only be reported.

WHY A BREACH RETURNS A NON-CONVERGENCE TERMINAL RATHER THAN BOUNCING DIRECTLY.
The clause requires a breach to "contribute to the same sanctioned
non-convergence/backlog disposition", and that disposition already exists:
`bounce_non_convergence_to_backlog` moves the item to `backlog`, surfaces it and
refuses to retry, keyed off `is_non_convergence_outcome`. So this gate produces a
failed outcome carrying `NON_CONVERGED_MARKER` in its detail — the sentinel that
predicate recognises — and the existing path does the rest. A second disposition
written here would be a second answer to "what happens to a non-converging
slice", and the two could drift.

WHY INVALID CEILING POLICY LEAVES THE GATE OBSERVATIONAL HERE. The pre-dispatch
wall already REFUSES a dispatch whose committed ceiling policy is invalid, before
any claim — so reaching this point with unresolvable policy means the
configuration changed mid-run. Refusing here would convert that into a
non-convergence bounce of work that may be perfectly sound, attributing a
configuration edit to the slice; so the reading is journaled with the policy
fault named and NO breach is manufactured, which is the same direction the clause
takes for every other unobservable measurement.

The whole evaluation is fail-soft in the sense that matters: every absence it can
encounter is already modelled as an explicit unobserved reason by the layers
below, so there is nothing here to swallow.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings import (
    resolve_adopted_cycle_ceilings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import fix_loop_count
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    read_journal_records_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    CompletedCycleSeries,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    NO_ADOPTED_CYCLE_CEILINGS,
    AdoptedCycleCeilings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_convergence import (
    CYCLE_CEILING_CONTRIBUTOR,
    PROGRESS_DEFICIT_CONTRIBUTOR,
    RuntimeConvergenceVerdict,
    runtime_convergence_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe import (
    gather_completed_cycle_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_projection import (
    cycle_journal_fields,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    FIX_LOOP_VISIT_CAP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_review_fix_cap,
    review_fix_visit_cap_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_REVIEW_FIX_CAP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_id_for
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CYCLE_CEILING_CONTRIBUTOR",
    "PRE_MERGE_BOUNDARY",
    "PROGRESS_DEFICIT_CONTRIBUTOR",
    "RUNTIME_CONVERGENCE_STAGE",
    "TERMINAL_BOUNDARY",
    "CycleGateSubject",
    "pre_merge_runtime_gate",
    "record_dispatch_runtime_convergence",
    "record_terminal_runtime_convergence",
]

# The journal stage both readings append, and the two boundary names. One
# literal each, shared by producer and consumer exactly as
# `NON_CONVERGENCE_BOUNCE_STAGE` is.
RUNTIME_CONVERGENCE_STAGE = "runtime-convergence"
PRE_MERGE_BOUNDARY = "pre-merge"
TERMINAL_BOUNDARY = "terminal"

# The stage a pre-merge runtime bounce reports as its own, so the terminal says
# WHERE the non-convergence was decided rather than only that it was.
_PRE_MERGE_STAGE = "pre-merge-convergence"

_CEILING_POLICY_ERRORS = (LivespecConfigUnreadableError, ConnectionPrefixMissingError)


@dataclass(frozen=True, kw_only=True)
class CycleGateSubject:
    """The inputs one dispatch fixes for BOTH boundary readings.

    Everything here is the same at the pre-merge boundary and at the terminal one:
    which repository and item the dispatch is for, the correlation its commits
    carry, the cap its fix loop runs under, and the two seams the reading writes
    and probes through. What differs between the readings -- the pull request
    known at that moment and the fix-loop count then observed -- stays a
    parameter of each call, so a function taking a subject names only what varies.
    Carrying them as one value is what keeps every seam within the repository's
    parameter budget honestly, rather than by suppressing the lint that flags it.
    """

    repo: Path
    item: WorkItem
    dispatch_id: str | None
    fix_loop_cap: int
    journal: JournalFile
    runner: CommandRunner


def pre_merge_runtime_gate(
    *,
    subject: CycleGateSubject,
    fix_loop_count: Callable[[], int],
) -> Callable[..., DispatchOutcome | None]:
    """Bind the pre-merge runtime gate to one dispatch.

    Returned as a CALLABLE taking the pull-request number the engine has just
    confirmed, because the engine must not import this module: it owns
    `DispatchOutcome`, which this module needs, and a mutual import would close
    a cycle. Handing the engine a bound gate also keeps its own surface to one
    optional parameter.
    """

    def gate(*, pr_number: int, run_id: str | None) -> DispatchOutcome | None:
        verdict, _ = _evaluate(
            subject=subject,
            pr_number=pr_number,
            fix_loop_count=fix_loop_count(),
            boundary=PRE_MERGE_BOUNDARY,
        )
        if not verdict.bounces:
            return None
        return DispatchOutcome(
            work_item_id=subject.item.id,
            status="failed",
            stage=_PRE_MERGE_STAGE,
            pr_number=pr_number,
            merge_sha=None,
            detail=f"{NON_CONVERGED_MARKER}: {verdict.as_reason()}",
            fabro_run_id=run_id,
        )

    return gate


def record_terminal_runtime_convergence(
    *,
    subject: CycleGateSubject,
    pr_number: int | None,
    fix_loop_count: int,
) -> RuntimeConvergenceVerdict:
    """Take and record the TERMINAL reading, whatever the run's outcome was.

    Runs on every terminal rather than only on a non-converged one: a run that
    merged still has a completed-cycle series worth recording, and the clause's
    calibration projection is a property of the terminal record rather than of
    the bounce. The returned verdict is what the bounce surfaces.
    """
    verdict, _ = _evaluate(
        subject=subject,
        pr_number=pr_number,
        fix_loop_count=fix_loop_count,
        boundary=TERMINAL_BOUNDARY,
    )
    return verdict


def record_dispatch_runtime_convergence(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> RuntimeConvergenceVerdict | None:
    """The TERMINAL reading, resolving its own inputs off this dispatch's journal.

    The post-run sequence's seam. It resolves the dispatch id and the fix-loop
    count from the SAME journal records calibration reads back, rather than
    taking them as parameters, for the reason `pr_open_diff_size` is read back
    rather than re-probed: the stage that observed each one wrote it down, and a
    second observation could not be shown to agree with what was recorded.

    FAIL-OPEN, mirroring the calibration and reflection stages beside it: the
    verdict is already final by the time this runs, so a probe fault or any
    unexpected error is journaled under its own `-error` stage and swallowed
    rather than crashing a dispatch that has finished. `None` is the honest
    return for a reading that was not taken.

    The fix-loop CAP is the graph's own `review_fix_visit_cap` for this item --
    the effective per-item cap plus the off-by-one `review_fix_visit_cap_for`
    spells once -- so the boundary this reading calls "the cap" is the boundary
    the dispatch actually rendered. An unreadable policy read degrades to the
    repository default, which is the same degradation the dispatch's own input
    render makes, and that identity is the point: the two are wrong together or
    right together.
    """
    taken = attempt(
        action=lambda: _terminal_reading(
            args=args, repo=repo, item=item, outcome=outcome, journal=journal
        ),
        exceptions=(AttributeError, OSError, RuntimeError),
    )
    if isinstance(taken, AttemptFailure):
        journal.append(
            record={
                "stage": f"{RUNTIME_CONVERGENCE_STAGE}-error",
                "work_item_id": item.id,
                "boundary": TERMINAL_BOUNDARY,
                "reason": type(taken.error).__name__,
            }
        )
        return None
    return taken


def _terminal_reading(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> RuntimeConvergenceVerdict:
    """The body the fail-open supervisor above guards."""
    records = read_journal_records_for(args=args, repo=repo)
    cap = unsafe_perform_io(
        effective_review_fix_cap(item=item, cwd=repo).value_or(DEFAULT_REVIEW_FIX_CAP)
    )
    return record_terminal_runtime_convergence(
        subject=CycleGateSubject(
            repo=repo,
            item=item,
            dispatch_id=dispatch_id_for(records=records, work_item_id=item.id),
            fix_loop_cap=review_fix_visit_cap_for(review_fix_cap=cap),
            journal=journal,
            runner=ShellCommandRunner(),
        ),
        pr_number=outcome.pr_number,
        fix_loop_count=fix_loop_count(records=records, work_item_id=item.id),
    )


def _evaluate(
    *,
    subject: CycleGateSubject,
    pr_number: int | None,
    fix_loop_count: int,
    boundary: str,
) -> tuple[RuntimeConvergenceVerdict, CompletedCycleSeries]:
    """The ONE evaluation both boundaries take, journaled as it is taken."""
    series = gather_completed_cycle_series(
        repo=subject.repo,
        item=subject.item,
        pr_number=pr_number,
        dispatch_id=subject.dispatch_id,
        runner=subject.runner,
    )
    resolved = attempt(
        action=lambda: resolve_adopted_cycle_ceilings(cwd=subject.repo),
        exceptions=_CEILING_POLICY_ERRORS,
    )
    unresolved = _policy_fault(resolved=resolved)
    verdict = runtime_convergence_verdict(
        series=series,
        ceilings=(
            resolved if isinstance(resolved, AdoptedCycleCeilings) else NO_ADOPTED_CYCLE_CEILINGS
        ),
        at_fix_loop_cap=fix_loop_count >= subject.fix_loop_cap,
        cap=FIX_LOOP_VISIT_CAP,
        cap_value=subject.fix_loop_cap,
    )
    subject.journal.append(
        record={
            "stage": RUNTIME_CONVERGENCE_STAGE,
            "work_item_id": subject.item.id,
            "boundary": boundary,
            "fix_loop_count": fix_loop_count,
            "fix_loop_cap": subject.fix_loop_cap,
            "ceiling_policy_unresolved": unresolved,
            **cycle_journal_fields(series=series, verdict=verdict),
        }
    )
    return verdict, series


def _policy_fault(*, resolved: object) -> str | None:
    """The ceiling-policy fault to name, or None when the policy resolved.

    Both unusable shapes collapse to one string because both say the same thing
    to this position: the committed ceilings cannot be read right now, so no
    comparison is made. The WALL is where the two are told apart and refused,
    before any claim.
    """
    if isinstance(resolved, AttemptFailure):
        return f"{type(resolved.error).__name__}: {resolved.error}"
    return resolved if isinstance(resolved, str) else None
