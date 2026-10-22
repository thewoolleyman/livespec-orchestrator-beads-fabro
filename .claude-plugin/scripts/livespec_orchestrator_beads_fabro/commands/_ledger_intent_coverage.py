"""How one ledger-intent scan DESCRIBES ITSELF to the detection-coverage anchor.

The detection coverage-record contract of `SPECIFICATION/contracts.md` makes
every detection invocation append an attributed ATTEMPT record to the
repository's designated anchor, and a COMPLETED-coverage record only from a run
that "reached a successful terminal outcome over its declared scope with EVERY
surfaced candidate durably disposed". This module owns the projection of one
scan into that run description, and nothing else.

THE WRITER IS NOT HERE. `_detection_coverage.record_detection_run` is the single
surface that may decide whether a completed record is claimable, and it is
reached unchanged: a scan that judged its own completeness would be the second
authority on the all-or-nothing rule, and the failure is silent by construction
because a wrongly-written completed record CLEARS the staleness fact derived
from it.

FOUR PROPERTIES AN EDITOR MUST NOT INVERT.

The record is written under the DRIFT operation, because the ledger-intent scan
is one of the two sources the `capture-spec-drift` clause names and the coverage
point both sources share is the drift frontier. A private operation name would
make the scan's records invisible to the staleness fact computed from that
operation, so a repository could run the scan for months while the fact kept
firing.

THE COVERAGE POINT IS SUPPLIED BY THE CALLER AND NEVER INVENTED. The drift
coverage point is the processed-merge FRONTIER, which only a caller that walked
those merges knows; a standalone scan has done half the detection, so inventing
one would clear the drift staleness fact on the strength of a pass that never
ran the impl-to-spec half. An absent point is not a failure — the shared writer
reports it as the reason the completed record was withheld, which is exactly
what it is.

AN UNJUDGED ITEM IS A SURFACED CANDIDATE. It is a candidate the run could not
dispose, so counting it keeps a run that could not read a verdict from claiming
coverage over the item it failed on — the one claim such a run must not make.

AND THE SCAN DISPOSES NOTHING, so `disposed_candidates` is empty by
construction rather than by omission. Disposition is "consented-and-filed" or
"consented-and-handed-off", both of which happen in the per-finding consent
flow of the skill above this CLI; a flag letting a caller assert a disposition
the scan never observed would turn the one unlocking input of a staleness-
clearing record into an unverifiable claim.

THE WRITE HALF DOES NOT FAIL SOFT, which is where it parts company with
`completed_coverage_point`'s read half. That read answers `None` for an anchor
naming no live row, because it runs inside the needs-attention composition and
one wrong config value must not take the whole snapshot down. Here the opposite
holds: the record is what the contract requires of the invocation, so an anchor
it could not write to is reported as a refusal naming the anchor rather than
swallowed — the expected `BeadsMappingError` is caught only to turn it into that
narration, never to continue as though the records had landed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    SUCCEEDED_OUTCOME,
    DetectionRun,
    detection_coverage_anchor,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "FAILED_OUTCOME",
    "ScanRecord",
    "declared_scope",
    "record_scan",
]

# The outcome word a non-zero scan carries. `SUCCEEDED_OUTCOME` is the one word
# the shared writer tests for, so anything else withholds the completed record;
# this one is named rather than inlined so the attempt record reads as a verdict
# rather than as an unexplained absence of the success word.
FAILED_OUTCOME = "failed"


@dataclass(frozen=True, kw_only=True)
class ScanRecord:
    """What the append did, as the caller has to act on it.

    `anchor_refused` is carried SEPARATELY from `narration` because the two owe
    opposite treatments: a withheld completed record is a narration about a
    successful scan and must not move its exit code, while an anchor the run
    could not write to is a precondition the contract requires and must. One
    optional string could not tell them apart, so a caller reading it would
    either fail every clean pass that withheld coverage or pass every run whose
    records were never written.
    """

    narration: str | None
    anchor_refused: bool


def declared_scope(*, since_version: int | None) -> str:
    """The scope this invocation covered, as the attempt record states it.

    The scope is what a later reader compares a completed point against, so a
    scoped and an unscoped run must not describe themselves the same way: an
    unscoped pass covers every live work-item as well, and reading a scoped
    run's record as an unscoped one would credit coverage it never took.
    """
    if since_version is None:
        return "ledger-intent scan: every live work-item plus every capture since the latest cut"
    return f"ledger-intent scan: every capture since the cut of v{since_version:03d}"


def record_scan(
    *,
    config: StoreConfig,
    project_root: Path,
    since_version: int | None,
    surfaced: tuple[str, ...],
    exit_code: int,
    coverage_point: str | None,
) -> ScanRecord:
    """Append this scan's records, and report what the operator must be told.

    The narration is owed on stderr whenever it is present: an aborted or
    partial pass that says nothing about its coverage reads to the operator
    exactly like one that succeeded, and the coverage point silently did not
    move.
    """
    anchor = detection_coverage_anchor(cwd=project_root)
    run = DetectionRun(
        operation=DRIFT_CAPTURE_OPERATION,
        scope=declared_scope(since_version=since_version),
        invoker=default_invoker_identity().invoker,
        outcome=SUCCEEDED_OUTCOME if exit_code == 0 else FAILED_OUTCOME,
        exit_code=exit_code,
        surfaced_candidates=surfaced,
        disposed_candidates=(),
        coverage_point=coverage_point,
    )
    appended = attempt(
        action=lambda: record_detection_run(path=config, anchor=anchor, run=run),
        exceptions=(BeadsMappingError,),
    )
    if isinstance(appended, AttemptFailure):
        detail = (
            f"the committed detection-coverage anchor {anchor!r} could not be "
            f"written to, so this invocation's records did not land: {appended.error}"
        )
        return ScanRecord(narration=detail, anchor_refused=True)
    recorded = appended
    if not is_successful(recorded):
        return ScanRecord(narration=recorded.failure().detail, anchor_refused=True)
    withheld = recorded.unwrap().withheld_reason
    if withheld is None:
        return ScanRecord(narration=None, anchor_refused=False)
    narration = f"no completed-coverage record was written: {withheld}"
    return ScanRecord(narration=narration, anchor_refused=False)
