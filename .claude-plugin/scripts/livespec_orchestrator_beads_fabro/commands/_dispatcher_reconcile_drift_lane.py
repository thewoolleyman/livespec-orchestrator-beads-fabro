"""The reconcile pass's drift lane: resolve the frontier, run the pass, record it.

The ONE caller that joins the per-merge pass to the committed
detection-coverage anchor. `_drift_run` enumerates and judges a range handed to
it; this module is where that range COMES FROM — the newest completed drift
coverage point on the anchor — and where the pass's own attempt and completed
records go back.

THE ALL-OR-NOTHING RULE IS NOT RE-IMPLEMENTED HERE, and that is the point of
this module's shape. The Records rule says a completed record is appended "ONLY
when the run reached a successful terminal outcome over its declared scope with
EVERY surfaced candidate durably disposed", and
`_detection_coverage.completed_coverage_is_claimable` is the single writer that
enforces exactly that — for the gap capture and for this pass alike. So the
lane's whole job on that question is to describe the pass HONESTLY in a
`DetectionRun`: every finding as a surfaced candidate, every FILED finding as a
disposed one, `partial_range` when any merge went unprocessed, and the
contiguous frontier as the coverage point. A second guard here would be a
second authority on one rule, and the two would drift in the direction nothing
announces — both producing a well-formed record.

That description is what makes a HELD finding stop the frontier without any
code here saying so: a held finding is surfaced and NOT disposed, so the
existing guard withholds the completed record and names it.

THE COVERAGE POINT IS THE CONTIGUOUS FRONTIER AND NOT THE NEWEST MERGE, even
though the guard only ever lets it through when the two are equal. Passing the
newest merge would make this lane correct only for as long as that guard keeps
its current shape; passing the prefix means the value is right on its own
terms, which is the difference between a safe value and a value that is
currently unreachable.

THE OPERATION NAME IS THE DRIFT CAPTURE'S OWN, deliberately. The frontier is
ONE value: the contract's drift-staleness fact names "the merges after the
frontier", singular, and this pass and the attended `capture-spec-drift` survey
both move it. A second operation key would give the repository two frontiers,
and the fact would count merges since whichever one its reader happened to ask
for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from returns.result import Result

from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    SUCCEEDED_OUTCOME,
    AnchorNotConfigured,
    DetectionRun,
    completed_coverage_point,
    detection_coverage_anchor,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._drift_run import run_drift_pass
from livespec_orchestrator_beads_fabro.commands._drift_run_frontier import (
    contiguous_frontier,
    scope_is_closed,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_merges import merge_range
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._detection_coverage import DetectionRunRecords
    from livespec_orchestrator_beads_fabro.commands._drift_run import (
        DriftRunOutcome,
        DriftRunSeams,
    )

__all__: list[str] = [
    "DriftLaneOutcome",
    "run_drift_lane",
]

_FAILED_OUTCOME = "failed"
_UNCONFIGURED = "no-tenant-connection"


@dataclass(frozen=True, kw_only=True)
class DriftLaneOutcome:
    """What one reconcile pass's drift lane did, as the pass itself can report it.

    `frontier` is the contiguous point this pass reached and `advanced` whether
    the completed record carrying it was actually written — which is the only
    thing that moves the repository's recorded frontier. The two differ on a
    partial scope, and a caller reading only the first would report an advance
    that did not happen.

    `withheld_reason` is populated precisely when `advanced` is False, carrying
    either the recorder's own reason or the measurement this lane could not
    take.
    """

    scope: str
    merges: tuple[str, ...]
    frontier: str | None
    filed: tuple[str, ...]
    held: tuple[str, ...]
    advanced: bool
    withheld_reason: str | None
    records: DetectionRunRecords | None


def run_drift_lane(*, repo: Path, invoker: str, seams: DriftRunSeams) -> DriftLaneOutcome:
    """Run the drift pass over the merges after the recorded frontier, and record it."""
    config = attempt(
        action=lambda: store_config(repo=repo),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError, OSError),
    )
    if isinstance(config, AttemptFailure):
        return DriftLaneOutcome(
            scope="",
            merges=(),
            frontier=None,
            filed=(),
            held=(),
            advanced=False,
            withheld_reason=_UNCONFIGURED,
            records=None,
        )
    anchor = detection_coverage_anchor(cwd=repo)
    frontier = completed_coverage_point(
        path=config, anchor=anchor, operation=DRIFT_CAPTURE_OPERATION
    )
    outcome = run_drift_pass(project_root=repo, frontier=frontier, seams=seams)
    scope = merge_range(since=frontier, ref="HEAD") if frontier else "every default-branch merge"
    recorded = record_detection_run(
        path=config,
        anchor=anchor,
        run=_detection_run(outcome=outcome, invoker=invoker, scope=scope),
    )
    return _lane_outcome(outcome=outcome, scope=scope, recorded=recorded)


def _detection_run(*, outcome: DriftRunOutcome, invoker: str, scope: str) -> DetectionRun:
    """This pass, described honestly for the one writer that grades it."""
    surfaced = tuple(finding.identity for judged in outcome.judged for finding in judged.findings)
    return DetectionRun(
        operation=DRIFT_CAPTURE_OPERATION,
        scope=_scope_detail(outcome=outcome, scope=scope),
        invoker=invoker,
        outcome=_FAILED_OUTCOME if _unprocessed(outcome=outcome) else SUCCEEDED_OUTCOME,
        exit_code=1 if _unprocessed(outcome=outcome) else 0,
        surfaced_candidates=surfaced,
        disposed_candidates=outcome.filed,
        partial_range=not scope_is_closed(judged=outcome.judged),
        coverage_point=contiguous_frontier(judged=outcome.judged),
    )


def _unprocessed(*, outcome: DriftRunOutcome) -> bool:
    """Whether any merge of the scope — or the enumeration itself — went unread."""
    return outcome.unreadable is not None or any(
        judged.failure is not None for judged in outcome.judged
    )


def _scope_detail(*, outcome: DriftRunOutcome, scope: str) -> str:
    """The DECLARED scope, plus the merges whose pass failed inside it.

    The declared range rather than the merges actually processed, because the
    Records rule's "declared scope" is what a partial pass is partial AGAINST —
    a scope rendered from the results would make every pass complete over its
    own output.

    The failed merges ride along because the attempt record is the only record
    a partial pass writes, and Scenario 207 requires it to NAME the failed
    merge: an attempt record carrying the range alone leaves an operator with
    no way to tell which of ten merges is holding the frontier.
    """
    failed = [judged.merge for judged in outcome.judged if judged.failure is not None]
    if outcome.unreadable is not None:
        return f"{scope} (not enumerated: {outcome.unreadable})"
    if not failed:
        return scope
    return f"{scope} (unprocessed merges: {', '.join(failed)})"


def _lane_outcome(
    *,
    outcome: DriftRunOutcome,
    scope: str,
    recorded: Result[DetectionRunRecords, AnchorNotConfigured],
) -> DriftLaneOutcome:
    """The lane's report, with the recorder's own verdict on the advance.

    `advanced` is read off the COMPLETED RECORD rather than off the frontier
    this pass computed, because only that record moves the repository's
    recorded frontier — and the recorder, not this lane, is what grades whether
    it may be written.
    """
    records = recorded.value_or(None)
    return DriftLaneOutcome(
        scope=scope,
        merges=outcome.merges,
        frontier=contiguous_frontier(judged=outcome.judged),
        filed=outcome.filed,
        held=outcome.held,
        advanced=records is not None and records.completed is not None,
        withheld_reason=_withheld_reason(records=records, recorded=recorded),
        records=records,
    )


def _withheld_reason(
    *,
    records: DetectionRunRecords | None,
    recorded: Result[DetectionRunRecords, AnchorNotConfigured],
) -> str | None:
    """Why the frontier did not move, or None when it did.

    An unconfigured anchor is reported as the recorder's own refusal DETAIL
    rather than as a reason of this lane's own wording: the two would say the
    same thing differently, and an operator comparing a lane report against a
    journal row would have to work out that they are one condition.
    """
    if records is not None:
        return records.withheld_reason
    refusal = recorded.swap().value_or(None)
    return None if refusal is None else refusal.detail
