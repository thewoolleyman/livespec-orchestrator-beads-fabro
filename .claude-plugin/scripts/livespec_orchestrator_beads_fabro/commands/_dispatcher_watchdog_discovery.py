"""The LISTING poll that discovers a watchdog's run, and its observability.

The watchdog cannot START keyed on a known run id: `fabro run` is BLOCKING
and only yields the run id on RETURN, i.e. after the run has already
finished. So each poll until the Dispatcher has bound one DISCOVERS the
in-flight run by attributing each `fabro ps -a --json --server <factory>`
row to a work-item through `_run_attribution` — the ledger's own run-id
stamp once the dispatch has written one, and the goal-text regex until then.

That is the ONLY window this module serves. Once a poll matches a row the
run id is bound, and `_dispatcher_watchdog_observation` takes every later
poll over to a per-run read: this listing scans every run the factory has
ever held, so re-running it each poll charged the dispatch for the
FACTORY'S HISTORY. That module records the measurement and owns the choice.

Discovery is the watchdog's single point of failure for its own window,
and it used to fail SILENTLY: a poll that matched nothing returned None,
the watch loop hit a bare `continue`, `decide_stall` was never consulted,
and the watchdog no-opped with ZERO output. Measured: that hid a TOTAL
watchdog outage on the `hp` remote factory for 11 days — the console
journal's entire history carries zero stall-cancel records — because a
blind watchdog and a watchdog watching a healthy run look identical from
outside.

The discovery step therefore lives HERE rather than in the launcher, as
one function that classifies AND journals: the "every poll is recorded"
guarantee is the point of the seam, and a caller that could take the
classification without the record would reintroduce the blind spot one
call site at a time.

Every failure mode the discovery step can take is a distinct `reason`, so
"the watchdog is blind" is a queryable state rather than an absence:

* `matched` — a ps row for this work-item is `runnable`/`running`.
* `ps-exit-nonzero` — the `fabro ps` probe itself failed; nothing was
  observed, so no conclusion about the run can be drawn.
* `no-ps-rows` — ps succeeded and listed NOTHING at all (a factory-wide
  observation, not an observation about this run).
* `work-item-id-mismatch` — ps listed rows, none carrying this work-item
  id. This is the leading hypothesis for the 11-day outage: a remote ps
  listing that omits an in-flight run mid-flight. `unattributed_row_count`
  discriminates it from the OTHER way this reason arises — a row that IS
  the run, whose goal text the id regex failed to attribute.
* `status-kind-not-running` — rows for this work-item exist but none is in
  a state the watchdog may act on (e.g. already terminal).

The evidence counters ride ALONGSIDE the reason deliberately: a reason
alone says which branch was taken, while the counters say what was
actually seen, which is what a later diagnosis of a discovery blind spot
needs. `classify_discovery` is a pure function of the ps result, so the
hermetic tier drives every branch without launching a real Fabro run; the
journal append through the injected writer is this module's only effect,
and the `fabro ps` call itself is issued by the sibling observation module
that chose this route.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPsResult,
    FabroRunSummary,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    GOAL_TEXT_ONLY,
    RunAttribution,
)

__all__: list[str] = [
    "ACTIONABLE_STATUS_KINDS",
    "DISCOVERY_JOURNAL_STAGE",
    "DISCOVERY_REASON_MATCHED",
    "DISCOVERY_REASON_NO_PS_ROWS",
    "DISCOVERY_REASON_PS_EXIT_NONZERO",
    "DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING",
    "DISCOVERY_REASON_WORK_ITEM_ID_MISMATCH",
    "DiscoveryOutcome",
    "classify_discovery",
    "journaled_discovery",
]

# The journal `stage` every discovery poll writes under. ONE stage name for
# both the matched and the unmatched outcomes, so "did the watchdog see
# anything this dispatch?" is a single stage filter rather than an
# inference from which records are missing.
DISCOVERY_JOURNAL_STAGE = "watchdog-discovery-poll"

DISCOVERY_REASON_MATCHED = "matched"
DISCOVERY_REASON_PS_EXIT_NONZERO = "ps-exit-nonzero"
DISCOVERY_REASON_NO_PS_ROWS = "no-ps-rows"
DISCOVERY_REASON_WORK_ITEM_ID_MISMATCH = "work-item-id-mismatch"
DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING = "status-kind-not-running"

# The run statuses the watchdog may act on. `runnable` is included because a
# queued run is still this dispatch's run (the stale-item reaper needs it);
# the watch loop separately refuses to stall-cancel anything not `running`.
# PUBLIC because the bound poll in `_dispatcher_watchdog_observation` grades
# the SAME statuses: two copies of this tuple would let one route start
# acting on a status the other had stopped acting on, and neither record
# would say so.
ACTIONABLE_STATUS_KINDS = ("runnable", "running")


@dataclass(frozen=True, kw_only=True)
class _DiscoveryEvidence:
    """What one ps poll actually saw, independent of which branch it took."""

    ps_exit_code: int
    ps_row_count: int
    work_item_row_count: int
    unattributed_row_count: int
    status_kinds: tuple[str | None, ...]


@dataclass(frozen=True, kw_only=True)
class DiscoveryOutcome:
    """One poll's discovery result plus the evidence the reason was read from."""

    run: FabroRunSummary | None
    reason: str
    ps_exit_code: int
    ps_row_count: int
    work_item_row_count: int
    unattributed_row_count: int
    status_kinds: tuple[str | None, ...]


def journaled_discovery(
    *,
    work_item_id: str,
    ps: FabroPsResult,
    journal: JournalWriter,
    attribution: RunAttribution = GOAL_TEXT_ONLY,
) -> FabroRunSummary | None:
    """Classify one ps poll, record it unconditionally, and return the run.

    The append is UNCONDITIONAL and happens on EVERY poll. A record per poll
    is deliberately chatty; the alternative — recording only the misses, or
    only the changes — leaves the all-misses case looking like the healthy
    case, which is exactly the shape that stayed unnoticed for 11 days.
    """
    outcome = classify_discovery(
        work_item_id=work_item_id,
        ps_exit_code=ps.command.exit_code,
        runs=ps.runs,
        attribution=attribution,
    )
    journal.append(record=_journal_record(work_item_id=work_item_id, outcome=outcome))
    return outcome.run


def classify_discovery(
    *,
    work_item_id: str,
    ps_exit_code: int,
    runs: tuple[FabroRunSummary, ...],
    attribution: RunAttribution = GOAL_TEXT_ONLY,
) -> DiscoveryOutcome:
    """Classify one `fabro ps` poll into a named discovery outcome.

    The ps exit code is checked FIRST: a failed probe observed nothing, so
    reporting it as "no matching row" would assert something about the run
    that was never measured.

    Which rows are "mine" is decided by `attribution`, not by re-reading the
    goal-derived id off the row. `work-item-id-mismatch` is the leading
    hypothesis for the 11-day outage precisely because a goal the id regex
    cannot parse produces a row that IS the run and reads as somebody else's;
    the ledger stamp answers that row directly, and the regex remains the floor
    for the window before the stamp lands.
    """
    mine = tuple(run for run in runs if attribution.owns(run=run, work_item_id=work_item_id))
    evidence = _DiscoveryEvidence(
        ps_exit_code=ps_exit_code,
        ps_row_count=len(runs),
        work_item_row_count=len(mine),
        unattributed_row_count=sum(
            1 for run in runs if attribution.work_item_id_for(run=run) is None
        ),
        status_kinds=tuple(run.status_kind for run in mine),
    )
    if ps_exit_code != 0:
        return _outcome(run=None, reason=DISCOVERY_REASON_PS_EXIT_NONZERO, evidence=evidence)
    for run in mine:
        if run.status_kind in ACTIONABLE_STATUS_KINDS:
            return _outcome(run=run, reason=DISCOVERY_REASON_MATCHED, evidence=evidence)
    return _outcome(run=None, reason=_miss_reason(runs=runs, mine=mine), evidence=evidence)


def _journal_record(*, work_item_id: str, outcome: DiscoveryOutcome) -> dict[str, object]:
    """Render one discovery outcome as a journal record.

    `matched` is carried as its own boolean rather than left implicit in
    `reason`, so the "was the watchdog ever able to see its run?" question a
    discovery blind spot poses is answerable without enumerating every
    reason name a future revision might add.
    """
    run = outcome.run
    return {
        "work_item_id": work_item_id,
        "stage": DISCOVERY_JOURNAL_STAGE,
        "matched": run is not None,
        "reason": outcome.reason,
        "ps_exit_code": outcome.ps_exit_code,
        "ps_row_count": outcome.ps_row_count,
        "work_item_row_count": outcome.work_item_row_count,
        "unattributed_row_count": outcome.unattributed_row_count,
        "status_kinds": list(outcome.status_kinds),
        "run_id": run.run_id if run is not None else None,
        "status_kind": run.status_kind if run is not None else None,
    }


def _miss_reason(
    *,
    runs: tuple[FabroRunSummary, ...],
    mine: tuple[FabroRunSummary, ...],
) -> str:
    """Name which of the three post-probe misses a successful ps poll took."""
    if not runs:
        return DISCOVERY_REASON_NO_PS_ROWS
    if not mine:
        return DISCOVERY_REASON_WORK_ITEM_ID_MISMATCH
    return DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING


def _outcome(
    *,
    run: FabroRunSummary | None,
    reason: str,
    evidence: _DiscoveryEvidence,
) -> DiscoveryOutcome:
    """Build the outcome from a run, a reason, and the shared evidence counters."""
    return DiscoveryOutcome(
        run=run,
        reason=reason,
        ps_exit_code=evidence.ps_exit_code,
        ps_row_count=evidence.ps_row_count,
        work_item_row_count=evidence.work_item_row_count,
        unattributed_row_count=evidence.unattributed_row_count,
        status_kinds=evidence.status_kinds,
    )
