"""How one watchdog poll OBSERVES its run, and what a per-run read means.

Sibling of `_dispatcher_watchdog_discovery`, which owns the LISTING poll.
This module owns the other half of the same rule (`contracts.md`, the
Dispatcher progress watchdog's "Observing the run" paragraph, and
Scenario 173) plus the choice between them:

* Until the Dispatcher has bound the dispatched run's id, the poll MAY
  discover the run by listing what the factory holds — the only route
  available, because `fabro run` is blocking and yields its id on RETURN.
* Once the id is bound, every later poll MUST read THAT run by its id and
  MUST NOT list the factory's runs again.

WHY THE LISTING HAD TO GO, in the numbers that decided it. `fabro ps -a`
scans every run the server has ever held, so a poll built on it costs what
the FACTORY'S HISTORY costs rather than what the dispatch costs. Measured
2026-10-12 against hp-xubuntu:32276 from the VPS: 1,605 rows, 9-17 s wall,
about 1.3-1.5 CPU-seconds and 100 MB per call — and with eight dispatches in
flight some nine of those listings ran at once, roughly 0.9 GB on the
dispatching host plus a full-store scan on the factory for every one.
`fabro inspect <run-id>` answered the same question in 1.1-1.5 s, about
0.15 CPU-seconds and 36 MB. Filtering the listing does NOT help, because the
server-side scan dominates: `--label` took 12-14 s and the running-only form
(no `-a`) took 30 s. Only asking about one run removes the growth term.

THE BOUND POLL'S REASONS. Two are shared verbatim with the discovery poll,
because they mean the same thing about the run whichever way it was
observed — which is what lets `matched` answer "could the watchdog see its
run?" across a dispatch whose polls changed mode partway through:

* `matched` — the read answered with a status the watchdog may act on.
* `status-kind-not-running` — it answered with one the watchdog may not
  (already terminal, say). The factory still holds the run.
* `run-not-held` — the factory answered that it holds NO SUCH RUN. A
  different fact from the one above and a different remedy: the run is gone
  rather than finished, so collapsing the two makes a vanished run read as
  a completed one.
* `run-read-unobservable` — the read FAILED, or answered something this
  module cannot interpret. It is NOT a disappearance and NOT a status: it
  is the absence of a reading, and the watchdog owes it exactly what it
  owes a listing that could not be read — nothing. The clause says so in as
  many words, and the direction matters: a failed probe reported as
  `run-not-held` is a confident claim about the factory earned from no
  evidence at all, which is the kind of finding nothing downstream
  re-examines.

The marker that separates the last two is therefore consulted ONLY where no
status could be read, and never on a reading that yielded one.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    FABRO_PROBE_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_discovery import (
    ACTIONABLE_STATUS_KINDS,
    DISCOVERY_REASON_MATCHED,
    DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING,
    journaled_discovery,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroRunSummary,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution

__all__: list[str] = [
    "BOUND_POLL_JOURNAL_STAGE",
    "BOUND_POLL_REASON_RUN_NOT_HELD",
    "BOUND_POLL_REASON_UNOBSERVABLE",
    "BoundPollOutcome",
    "ObservedRun",
    "classify_bound_poll",
    "journaled_bound_poll",
    "observed_run",
]

# The journal `stage` every BOUND poll writes under. A separate stage rather
# than a sixth discovery reason, because a shared record would have to carry
# `ps_row_count: 0` for a poll that listed nothing — a manufactured
# measurement, and exactly the shape the discovery record exists to refuse.
# The `matched` boolean and the two shared reason names are what keep the
# pair queryable together.
BOUND_POLL_JOURNAL_STAGE = "watchdog-bound-poll"

BOUND_POLL_REASON_RUN_NOT_HELD = "run-not-held"
BOUND_POLL_REASON_UNOBSERVABLE = "run-read-unobservable"

# The factory's own answer for a run it does not hold, lower-cased. Copied
# from the message `fabro dump` printed against hp-xubuntu:32276 on
# 2026-10-12 for run 01M4R5S6GST6XNQA10SGJ9TA2H — a leading cross glyph then
# "No run found matching '<id>' (tried run ID prefix and workflow name)" —
# rather than paraphrased, because a reconstructed phrase is the shape that
# matches nothing and then reports the absence as a measurement.
#
# A READING THAT YIELDED A STATUS IS NEVER SCANNED FOR IT. `fabro inspect`
# echoes the run's whole `run_spec`, rendered goal included, so any run whose
# brief QUOTES this message carries the marker in a perfectly healthy
# payload — this very work-item's goal does. The marker is therefore consulted
# only where no status could be read at all, which is the one reading it can
# say anything about.
_RUN_NOT_HELD_MARKER = "no run found"


@dataclass(frozen=True, kw_only=True)
class ObservedRun:
    """One poll's observation: the run, and the record the read returned.

    `record` is the PER-RUN read's own payload, or None on the listing route
    and on any read that yielded none. It is carried rather than discarded so a
    caller needing a FIELD of the run's record reads it from the SAME reading
    that answered where the run is -- the whole-run wall budget's `running`
    instant is the one such field today, and a second `fabro inspect` for it
    would be both a second round trip per dispatch and a second answer nothing
    announces the divergence between.

    It is the RAW payload rather than any interpretation of it, because what a
    field MEANS is the reader's concern: this module answers "could the watchdog
    see its run?", and a budget instant, a park instant and a cost figure are
    three different questions about one reading.
    """

    run: FabroRunSummary | None
    record: object | None


@dataclass(frozen=True, kw_only=True)
class BoundPollOutcome:
    """One bound-run poll's result plus the reading its reason was taken from.

    `run_id` is the run the poll ASKED about and is populated whatever the
    reason, while `run` is populated only where the read found it in a state
    the watchdog may act on. Keeping both is what lets a poll that saw nothing
    still name its subject: a record naming no run would be indistinguishable
    from a poll that never happened, which is the silent shape this whole seam
    exists to refuse.
    """

    run_id: str
    run: FabroRunSummary | None
    reason: str
    inspect_exit_code: int
    status_kind: str | None


def observed_run(
    *,
    work_item_id: str,
    port: FabroPort,
    journal: JournalWriter,
    attribution: RunAttribution,
    bound_run_id: str | None,
) -> ObservedRun:
    """Take this poll's one observation of the run, by whichever route applies.

    `bound_run_id` alone decides the route, and it is the only thing that may:
    a poll that chose by anything else — a retry counter, a probe that failed,
    a configuration key — could fall back to listing on a dispatch whose id was
    bound, which is the growth term this seam removes.

    It lives here rather than in the launcher for the reason its listing
    sibling gives: each route classifies AND journals as one act, so no caller
    can take the result without leaving the record.
    """
    if bound_run_id is not None:
        inspect = port.inspect(
            run_id=bound_run_id,
            timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS,
        )
        return ObservedRun(
            run=journaled_bound_poll(
                work_item_id=work_item_id,
                run_id=bound_run_id,
                inspect=inspect,
                journal=journal,
            ),
            record=inspect.payload,
        )
    # The LISTING route carries no per-run record: a `ps` row answers what the
    # factory holds, and the fields a caller reads off a run's own record are
    # not on it. None is that absence rather than a reading that found nothing.
    return ObservedRun(
        run=journaled_discovery(
            work_item_id=work_item_id,
            ps=port.ps(timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS),
            journal=journal,
            attribution=attribution,
        ),
        record=None,
    )


def journaled_bound_poll(
    *,
    work_item_id: str,
    run_id: str,
    inspect: FabroInspectResult,
    journal: JournalWriter,
) -> FabroRunSummary | None:
    """Classify one per-run read of a BOUND run, record it, and return the run.

    The append is UNCONDITIONAL and happens on EVERY poll, for the reason its
    listing sibling gives: recording only the misses, or only the changes,
    leaves the all-misses case looking exactly like the healthy case.
    """
    outcome = classify_bound_poll(
        work_item_id=work_item_id,
        run_id=run_id,
        inspect_exit_code=inspect.command.exit_code,
        status_kind=inspect.status_kind,
        output=f"{inspect.command.stdout}\n{inspect.command.stderr}",
    )
    journal.append(record=_bound_poll_record(work_item_id=work_item_id, outcome=outcome))
    return outcome.run


def classify_bound_poll(
    *,
    work_item_id: str,
    run_id: str,
    inspect_exit_code: int,
    status_kind: str | None,
    output: str,
) -> BoundPollOutcome:
    """Classify one `fabro inspect <run-id>` reading of an already-bound run.

    The run id is an INPUT rather than something read back out of the payload.
    The Dispatcher bound it, so the poll already knows which run it asked
    about, and re-deriving it would make a payload this module could not parse
    look like a poll about no run in particular.

    The LADDER IS ORDERED, and the order is the whole defence against reading
    a healthy run as a vanished one: a reading that yielded a status is
    graded on that status and never scanned, and only a reading that yielded
    none is asked whether the factory refused to find the run at all.
    """
    if inspect_exit_code == 0 and status_kind is not None:
        return _read_status(work_item_id=work_item_id, run_id=run_id, status_kind=status_kind)
    if _RUN_NOT_HELD_MARKER in output.casefold():
        return _outcome(
            run_id=run_id,
            run=None,
            reason=BOUND_POLL_REASON_RUN_NOT_HELD,
            inspect_exit_code=inspect_exit_code,
            status_kind=status_kind,
        )
    return _outcome(
        run_id=run_id,
        run=None,
        reason=BOUND_POLL_REASON_UNOBSERVABLE,
        inspect_exit_code=inspect_exit_code,
        status_kind=status_kind,
    )


def _read_status(*, work_item_id: str, run_id: str, status_kind: str) -> BoundPollOutcome:
    """Grade a reading that DID yield a status for the bound run."""
    actionable = status_kind in ACTIONABLE_STATUS_KINDS
    return _outcome(
        run_id=run_id,
        run=_bound_run(work_item_id=work_item_id, run_id=run_id, status_kind=status_kind)
        if actionable
        else None,
        reason=DISCOVERY_REASON_MATCHED if actionable else DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING,
        inspect_exit_code=0,
        status_kind=status_kind,
    )


def _bound_run(*, work_item_id: str, run_id: str, status_kind: str | None) -> FabroRunSummary:
    """The run row a per-run read stands in for.

    `goal` and `total_usd_micros` are None because the per-run read was never
    asked for them — the question was "what is THIS run doing", not "what is
    every run this factory holds". Carrying the work-item id is honest for the
    mirror reason: the Dispatcher bound this run to this item, so it is a fact
    about the dispatch rather than a value re-parsed out of rendered prose.
    """
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None,
        total_usd_micros=None,
        work_item_id=work_item_id,
    )


def _outcome(
    *,
    run_id: str,
    run: FabroRunSummary | None,
    reason: str,
    inspect_exit_code: int,
    status_kind: str | None,
) -> BoundPollOutcome:
    """Build the bound-poll outcome from a run, a reason, and the reading."""
    return BoundPollOutcome(
        run_id=run_id,
        run=run,
        reason=reason,
        inspect_exit_code=inspect_exit_code,
        status_kind=status_kind,
    )


def _bound_poll_record(*, work_item_id: str, outcome: BoundPollOutcome) -> dict[str, object]:
    """Render one bound-run poll as a journal record.

    `matched` carries the SAME meaning it carries on a discovery record, so
    "was the watchdog ever able to see its run?" stays one filter across a
    dispatch whose polls changed mode partway through.
    """
    return {
        "work_item_id": work_item_id,
        "stage": BOUND_POLL_JOURNAL_STAGE,
        "matched": outcome.run is not None,
        "reason": outcome.reason,
        "run_id": outcome.run_id,
        "inspect_exit_code": outcome.inspect_exit_code,
        "status_kind": outcome.status_kind,
    }
