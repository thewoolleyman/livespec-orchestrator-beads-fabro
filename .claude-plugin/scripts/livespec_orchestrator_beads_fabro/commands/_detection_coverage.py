"""Detection-run records on the committed detection-coverage anchor.

The detection coverage-record contract in `SPECIFICATION/contracts.md` makes
detection recency RECORDED and its staleness COMPUTED, never remembered. Every
invocation of `capture-impl-gaps` or `capture-spec-drift` appends an attributed
ATTEMPT record to the repository's designated coverage anchor; a
COMPLETED-coverage record — the one that MOVES the coverage point — is appended
only when the run reached a successful terminal outcome over its declared scope
with every surfaced candidate durably disposed.

⛔ THE ALL-OR-NOTHING RULE IS THE WHOLE POINT, AND IT FAILS IN ONE DIRECTION.
A completed record written by a run that half-finished does not merely record
something inaccurate: it CLEARS the staleness fact derived from it, so the
convergence engine goes quiet on the strength of a pass that never happened.
The failure is silent by construction — the record looks exactly like a good
one — so the guard cannot live at the call sites, where each caller would have
to remember every disqualifying condition. It lives HERE, in
`completed_coverage_is_claimable`, and `record_detection_run` is the single
writer that consults it. A caller can only ever ASK for a completed record; it
cannot assert one.

The anchor itself is provisioned ONCE by the operator through
`capture-work-item` (consent-native) and its id is committed in
`.livespec.jsonc`. `detection_coverage_anchor` deliberately never invents one:
an unset key answers None and the writer refuses, because appending coverage
bookkeeping to a guessed id would either fail loudly against a stranger's item
or, worse, succeed against one.

THE SELF-BOOKKEEPING EXCEPTION IS SCOPED TO THIS MODULE. Appending these two
record types is the ONLY ledger write the detection operations may perform
outside their consent flows — no work-item create, no disposition, no edit of
any other record. That is enforceable by reading this file: the client seam is
reached exactly twice below, once for `add_comment` and once (through
`read_work_item_comments`) for the read-back, and both name the anchor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ATTEMPT_MARKER_PREFIX",
    "COMPLETED_MARKER_PREFIX",
    "DRIFT_CAPTURE_OPERATION",
    "GAP_CAPTURE_OPERATION",
    "SUCCEEDED_OUTCOME",
    "AnchorNotConfigured",
    "DetectionRun",
    "DetectionRunRecords",
    "attempt_record_present",
    "completed_coverage_is_claimable",
    "completed_coverage_point",
    "detection_coverage_anchor",
    "record_detection_run",
    "undisposed_candidates",
]

GAP_CAPTURE_OPERATION = "capture-impl-gaps"
DRIFT_CAPTURE_OPERATION = "capture-spec-drift"
SUCCEEDED_OUTCOME = "succeeded"

ATTEMPT_MARKER_PREFIX = "livespec-detection-attempt: "
COMPLETED_MARKER_PREFIX = "livespec-detection-completed: "

_ANCHOR_KEY = "detection_coverage_anchor"
_OPERATION_FIELD = "operation"
_SCOPE_FIELD = "scope"
_COVERAGE_POINT_FIELD = "coverage_point"


@dataclass(frozen=True, kw_only=True)
class AnchorNotConfigured:
    """No detection-coverage anchor is committed, so no record can be written."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class DetectionRun:
    """One detection invocation, as its own records will describe it.

    `surfaced_candidates` and `disposed_candidates` are the run's own candidate
    keys: a gap id for `capture-impl-gaps`, a finding key for
    `capture-spec-drift`. "Durably disposed" means consented-and-filed,
    consented-and-handed-off, or explicitly declined on the record — a skipped
    or deferred candidate is NOT disposed, and is exactly the case that must
    leave the prior coverage point standing.

    `coverage_point` is the point a COMPLETED record would carry: the ratified
    spec revision the gap capture ran against, or the default-branch merge SHA
    the drift pass ran through.
    """

    operation: str
    scope: str
    invoker: str
    outcome: str
    exit_code: int
    surfaced_candidates: tuple[str, ...] = ()
    disposed_candidates: tuple[str, ...] = ()
    partial_range: bool = False
    coverage_point: str | None = None


@dataclass(frozen=True, kw_only=True)
class DetectionRunRecords:
    """What `record_detection_run` actually appended, and why.

    `withheld_reason` is populated precisely when `completed` is None. It is
    part of the return value rather than a log line because the operator has to
    be told that the coverage point did NOT move — an aborted pass that says
    nothing reads as a pass that succeeded.
    """

    attempt: str
    completed: str | None
    withheld_reason: str | None


def detection_coverage_anchor(*, cwd: Path) -> str | None:
    """The committed `dispatcher.detection_coverage_anchor` id, or None when unset.

    An absent key and an empty string — the committed spelling of "not yet
    provisioned" — both answer None. Reads through the shared public
    `dispatcher_block` seam, which raises a truthful
    `LivespecConfigUnreadableError` when `.livespec.jsonc` will not parse
    rather than folding that into "nothing is configured here".
    """
    raw = dispatcher_block(cwd=cwd).get(_ANCHOR_KEY)
    if isinstance(raw, str) and raw.strip() != "":
        return raw.strip()
    return None


def undisposed_candidates(*, run: DetectionRun) -> tuple[str, ...]:
    """The surfaced candidates this run did not durably dispose, in order."""
    disposed = frozenset(run.disposed_candidates)
    return tuple(key for key in run.surfaced_candidates if key not in disposed)


def completed_coverage_is_claimable(*, run: DetectionRun) -> str | None:
    """None when a COMPLETED record is claimable; else the reason it is not.

    Every disqualifying condition the contract enumerates is checked here and
    nowhere else: a non-successful outcome, a non-zero exit, a partial range,
    an undisposed candidate, and a run that never resolved a coverage point to
    claim in the first place.
    """
    if run.outcome != SUCCEEDED_OUTCOME:
        return f"outcome is {run.outcome!r}, not {SUCCEEDED_OUTCOME!r}"
    if run.exit_code != 0:
        return f"exit code is {run.exit_code}, not 0"
    if run.partial_range:
        return "the declared scope was covered only partially"
    undisposed = undisposed_candidates(run=run)
    if undisposed:
        return f"{len(undisposed)} surfaced candidate(s) undisposed: {', '.join(undisposed)}"
    if run.coverage_point is None:
        return "the run resolved no coverage point to claim"
    return None


def record_detection_run(
    *,
    path: StoreConfig,
    anchor: str | None,
    run: DetectionRun,
) -> Result[DetectionRunRecords, AnchorNotConfigured]:
    """Append this run's records to the anchor: always an attempt, maybe a completion.

    The ONLY ledger write the detection operations perform outside their
    consent flows, and it touches nothing but `anchor`.
    """
    if anchor is None or anchor.strip() == "":
        return Failure(
            AnchorNotConfigured(
                detail=(
                    "no dispatcher.detection_coverage_anchor is committed in "
                    ".livespec.jsonc; provision the anchor once through "
                    "capture-work-item and commit its id before running detection"
                )
            )
        )
    client = make_beads_client(config=path)
    attempt_body = ATTEMPT_MARKER_PREFIX + _encode(fields=_attempt_fields(run=run))
    client.add_comment(issue_id=anchor, body=attempt_body)
    withheld = completed_coverage_is_claimable(run=run)
    if withheld is not None:
        return Success(
            DetectionRunRecords(attempt=attempt_body, completed=None, withheld_reason=withheld)
        )
    completed_body = COMPLETED_MARKER_PREFIX + _encode(fields=_completed_fields(run=run))
    client.add_comment(issue_id=anchor, body=completed_body)
    return Success(
        DetectionRunRecords(attempt=attempt_body, completed=completed_body, withheld_reason=None)
    )


def completed_coverage_point(
    *,
    path: StoreConfig,
    anchor: str | None,
    operation: str,
) -> str | None:
    """The newest COMPLETED coverage point recorded for `operation`, or None.

    Fail-soft per record, mirroring `read_work_item_comments`: a comment whose
    payload does not parse, or which names a different operation, is skipped
    rather than blinding the read. None means "no completed pass on record",
    which is the same answer an unconfigured anchor gives — in both cases every
    ratified revision and every merge is unaccounted for, and the staleness
    facts must fire.

    ⚠ FAIL-SOFT ON A MISSING ANCHOR ITEM HERE, AND ONLY HERE. A committed
    anchor id that names no live ledger row — a typo, or an item since
    deleted — makes `bd comments` fail, and this read runs inside the
    needs-attention composition: letting that escape would take the WHOLE
    attention snapshot down for one wrong config value, hiding every unrelated
    fact behind it. Answering None instead is the fail-CLOSED direction for
    this question, because "no completed pass on record" is exactly what makes
    both staleness facts fire, so the operator is told to run detection rather
    than told nothing. The WRITE half deliberately does NOT do this: a bad
    anchor at record time must fail loudly at the caller's supervisor boundary,
    because silently swallowing it would drop the record the contract requires.
    """
    point: str | None = None
    for fields in _anchor_records(path=path, anchor=anchor, prefix=COMPLETED_MARKER_PREFIX):
        if fields.get(_OPERATION_FIELD) != operation:
            continue
        recorded = fields.get(_COVERAGE_POINT_FIELD)
        if isinstance(recorded, str) and recorded != "":
            point = recorded
    return point


def attempt_record_present(
    *,
    path: StoreConfig,
    anchor: str | None,
    operation: str,
    scope: str,
) -> bool:
    """Whether an ATTEMPT record for `operation` over exactly `scope` is on record.

    The question a caller asks before re-recording a state that cannot have
    changed since it last recorded it. `bd comments` offers neither edit nor
    delete, so a record appended once per tick of a ten-minute timer is
    permanent noise; a caller able to recognise its own previous record can
    write that record once instead.

    MATCHED ON THE DECLARED SCOPE, and on nothing else the record carries. The
    scope is what a record is a record OF, and it is the only field that is
    identical across two invocations describing one unchanged repository state:
    an invoker differs between the host timer and an operator, and an outcome
    is the very thing a caller de-duplicating an inert state is disputing. So a
    caller matches against a scope string it WRITES verbatim rather than
    against a shape it has to reconstruct.

    FAIL-SOFT EXACTLY AS THE COMPLETED READ ABOVE IS, and in the same
    direction: an absent anchor, or comments this cannot read, answers False,
    so the caller RECORDS rather than skips. The opposite default would let one
    blinded read suppress the record the contract does owe, which is the
    expensive direction — a suppressed record is permanent in the same way an
    appended one is.
    """
    return any(
        fields.get(_OPERATION_FIELD) == operation and fields.get(_SCOPE_FIELD) == scope
        for fields in _anchor_records(path=path, anchor=anchor, prefix=ATTEMPT_MARKER_PREFIX)
    )


def _anchor_records(
    *,
    path: StoreConfig,
    anchor: str | None,
    prefix: str,
) -> tuple[dict[str, Any], ...]:
    """Every decoded record of one marker kind on the anchor, oldest first.

    The ONE read behind both public readings above, so the fail-soft rule each
    of them documents is applied once rather than restated. A second walk of
    the same comments would be a second place for that rule to be got wrong,
    and it would be got wrong silently: both readings would still answer.
    """
    if anchor is None or anchor.strip() == "":
        return ()
    comments = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=anchor),
        exceptions=(BeadsMappingError,),
    )
    if isinstance(comments, AttemptFailure):
        return ()
    return tuple(
        _decode(payload=comment.text.removeprefix(prefix))
        for comment in comments
        if comment.text.startswith(prefix)
    )


def _attempt_fields(*, run: DetectionRun) -> dict[str, Any]:
    return {
        _OPERATION_FIELD: run.operation,
        _SCOPE_FIELD: run.scope,
        "invoker": run.invoker,
        "outcome": run.outcome,
        "exit_code": run.exit_code,
        "surfaced": len(run.surfaced_candidates),
        "disposed": len(run.disposed_candidates),
    }


def _completed_fields(*, run: DetectionRun) -> dict[str, Any]:
    return {
        _OPERATION_FIELD: run.operation,
        _COVERAGE_POINT_FIELD: run.coverage_point,
        _SCOPE_FIELD: run.scope,
        "invoker": run.invoker,
    }


def _encode(*, fields: dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True)


def _decode(*, payload: str) -> dict[str, Any]:
    parsed = parse_json(text=payload)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return {}
    return dict(cast("dict[str, Any]", parsed))
