"""The two LEDGER adapters of the shared result reader: item status and item marker.

Both read the named repository's own tenant through the ordinary client seam, with
the connection resolved from that repository's clone so the `bd` call executes
there — the cross-tenant execution requirement of the
shared-authoritative-result-reader clause in `SPECIFICATION/contracts.md`.

WHY THE COMMENT ADAPTER'S OWN DETAIL CARRIES THE NARROWING. The clause says
comment-marker satisfaction proves only the requested marker's presence and MUST
NOT stand in for completed implementation or verified proof. A satisfied
observation is what a caller quotes onward, so the narrowing rides on the
observation rather than living only in the clause — and it rides on the SATISFIED
arm specifically, because that is the arm that can be mistaken for a stronger
claim.

WHY THE MARKER MATCH IS EXACT AND IS NEVER NORMALIZED. The target names an exact
marker, and a marker is chosen to be unambiguous. Whitespace-folding it the way
this repository's proof-record reader folds assertion text would make
`delivered: no` match a request for `delivered`, which is the fail-open
direction; the reader of a wrapped marker is the one who should choose a marker
that does not wrap.

AND WHY A MARKER IS ONLY FOUND WHERE A RECORD OPENS, which is the other half of
the same fail-open question and the one that was measured. A marker names a
RECORD KIND, and every record this reader answers for is a comment whose FIRST
LINE opens with its marker: a plan Proof of Done record's first line is
`Plan Proof of Done — <verdict> — …`, and a completeness-review evidence
comment's first line is `plan-completeness-review-evidence`. Scanning whole
comment bodies instead matched the marker wherever it was MENTIONED — and the
plan's own bookkeeping mentions it on every write. Every sanctioned pointer write
appends a `plan-progress-event` whose payload serializes the obligation's own
`required_result`, marker included, so an `item_comment` obligation naming the
plan epic was satisfied by the comment that RECORDED it, the instant it was
recorded; a scope event quoting the marker in prose did the same. Measured
2026-10-20 on plan epic `bd-ib-fyozyd` and again 2026-10-21 on
`livespec-dev-tooling-mvalxq`: the proof pointer self-satisfied, the resume
derived the review pointer, that pointer self-satisfied in its turn, and the plan
skipped proof and review while every surface read as a correctly advancing chain.

The placement rule is deliberately the FAIL-CLOSED one, and it binds whoever
authors an obligation by hand as well as the two legs derived here: a marker that
does not open the record it names is never satisfied, so such an obligation
stalls its plan diagnosably rather than discharging itself silently. Narrowing by
SKIPPING the known event prefixes instead would have left every other comment —
a handoff entry, an operator rider, a relay event — able to discharge an
obligation by quoting it, which is the same defect reached through a different
comment kind.

WHY THE COMMENT EVIDENCE PREFERS AN ID, THEN A TIMESTAMP, THEN A POSITION. The
clause asks for a "ledger comment/version" identity, and a real `bd comments`
record carries an id. Where the substrate omits it the creation instant is the
next best identity, and where that too is absent the comment's position in the
item's own comment order is the only thing left that distinguishes two comments
of the same item. Reporting a positional identity is honest; reporting an empty
one would read as a comment nobody could find again.

A STATUS READ'S EVIDENCE IS THE RECORD PLUS THE STATUS IT WAS READ AT. A ledger
record has no version an operator can cite independently of the field being
observed, so the record id and the observed status together are the evidence —
which is also what makes a satisfied and an unsatisfied status observation
comparable: the two differ in exactly the field under test.

AND THE STATUS COMPARISON GOES THROUGH THE ADAPTER, NEVER BY STRING EQUALITY.
The two sides are written in two vocabularies. An obligation names a WORK-ITEM
LIFECYCLE status, whose terminal name is `done`; the record carries the stored
BEADS-NATIVE status, which the work-item beads-issue mapping of
`SPECIFICATION/contracts.md` spells `closed` for exactly that lifecycle state.
Comparing the two spellings directly therefore reported an item that had been
closed for hours as standing somewhere else, so an obligation naming `done` was
unsatisfiable for the rest of its plan's budget — and the fault did not look
like one, because every surface reported a well-formed `unsatisfied` reading
quoting the real stored status. Measured 2026-10-21 on plan epic
`bd-ib-jxvgq5`, whose chain obligation named `item_status bd-ib-rszkjc status
done` while the ledger held that item at `closed`.

Both sides are normalized onto the LIFECYCLE vocabulary rather than the target
alone being mapped onto the stored one, and the symmetry is the point: this
tenant holds obligations in both spellings — `_plan_resume_advance` derives its
own with the native `closed` literal while a hand-authored plan obligation names
`done` — so normalizing both makes "either vocabulary reaches the same verdict"
a property of the comparison rather than a special case that has to be kept in
step with whichever side is thought to be canonical.

The EVIDENCE and the DETAIL still quote the status the ledger STORES, unmapped.
The mapping decides how two names are compared; it is not a rewriting of what
was observed, and an operator told an item stands at a status the store does not
hold has been pointed at the wrong record.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro._store_statuses import livespec_status_for
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_LEDGER,
    ResultObservation,
    satisfied,
    unobservable,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    result_store_config,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ItemCommentTarget,
    ItemStatusTarget,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

__all__: list[str] = [
    "MARKER_NARROWING",
    "UNRESOLVED_CONNECTION",
    "observe_item_comment",
    "observe_item_status",
]

# The clause's own narrowing, in one place so the satisfied comment observation
# and any later renderer of it cannot word it differently.
MARKER_NARROWING = (
    "marker presence proves only the requested marker, never completed"
    " implementation and never a verified proof"
)

# The EXPECTED-error surface ONE tenant read can raise. Catching exactly this set
# — never a blanket except — is what keeps an unreachable, unconfigured or absent
# tenant an unobservable read instead of a traceback.
_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    BeadsConnectionError,
    BeadsCommandError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_STATUS_FIELD = "status"

# The one diagnostic both ledger adapters share, worded once so a reader of
# either observation is pointed at the same thing to fix.
UNRESOLVED_CONNECTION = (
    "the named repository's own configuration did not resolve a tenant connection"
)


def observe_item_status(
    *, repository: ResultRepository, target: ItemStatusTarget, now: str
) -> ResultObservation:
    """Observe whether one ledger item stands at the expected status."""
    config = result_store_config(repository=repository)
    if config is None:
        return _unreadable(
            repository=repository, target=target, now=now, detail=UNRESOLVED_CONNECTION
        )
    read = attempt(
        action=lambda: make_beads_client(config=config).show_issue(issue_id=target.item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return _unreadable(
            repository=repository,
            target=target,
            now=now,
            detail=f"the ledger read of {target.item_id} failed: {_named(failure=read)}",
        )
    status: object = read.get(_STATUS_FIELD)
    if not isinstance(status, str) or status == "":
        return _unreadable(
            repository=repository,
            target=target,
            now=now,
            detail=(
                f"the ledger record for {target.item_id} carries no readable status,"
                " so it is evidence of nothing about where the item stands"
            ),
        )
    if livespec_status_for(status=status) != livespec_status_for(status=target.status):
        return unsatisfied(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_LEDGER,
            now=now,
            evidence=f"ledger record {target.item_id} at status {status}",
            detail=(
                f"the ledger reports {target.item_id} at status {status}, not the"
                f" expected {target.status}"
            ),
        )
    return satisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_LEDGER,
        now=now,
        evidence=f"ledger record {target.item_id} at status {status}",
        detail=(
            f"the ledger reports {target.item_id} at status {status}, which is the"
            f" expected {target.status}"
        ),
    )


def observe_item_comment(
    *, repository: ResultRepository, target: ItemCommentTarget, now: str
) -> ResultObservation:
    """Observe whether one ledger item carries a RECORD of the requested marker.

    A record is a comment whose first line opens with the marker; a comment that
    merely mentions it is not one. The module docstring carries the measurement.
    """
    config = result_store_config(repository=repository)
    if config is None:
        return _unreadable(
            repository=repository, target=target, now=now, detail=UNRESOLVED_CONNECTION
        )
    read = attempt(
        action=lambda: read_work_item_comments(path=config, work_item_id=target.item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return _unreadable(
            repository=repository,
            target=target,
            now=now,
            detail=(
                f"the ledger comment read of {target.item_id} failed:" f" {_named(failure=read)}"
            ),
        )
    comments = tuple(read)
    for position, comment in enumerate(comments, start=1):
        if not _opens_record(text=comment.text, marker=target.marker):
            continue
        identity = comment.comment_id or comment.created_at or f"position {position}"
        return satisfied(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_LEDGER,
            now=now,
            evidence=f"ledger comment {identity} on {target.item_id}",
            detail=(
                f"ledger comment {identity} on {target.item_id} carries the exact"
                f" marker {target.marker!r}; {MARKER_NARROWING}"
            ),
        )
    return unsatisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_LEDGER,
        now=now,
        evidence=f"{len(comments)} ledger comment(s) read on {target.item_id}",
        detail=(
            f"none of the {len(comments)} comment(s) on {target.item_id} opens with"
            f" the marker {target.marker!r}, so the item carries no record of that"
            " kind; a comment that merely mentions the marker is not one"
        ),
    )


def _opens_record(*, text: str, marker: str) -> bool:
    """Whether one comment is a RECORD of the requested marker's kind.

    The FIRST line decides it, and nothing is stripped first: every record this
    reader answers for is rendered with its marker as the comment's leading
    bytes, so tolerating a leading blank line or indentation would widen the
    match to shapes no writer here produces, in the one direction the module
    docstring records as the measured defect.
    """
    first_line, _, _ = text.partition("\n")
    return first_line.startswith(marker)


def _unreadable(
    *,
    repository: ResultRepository,
    target: ItemStatusTarget | ItemCommentTarget,
    now: str,
    detail: str,
) -> ResultObservation:
    """One unobservable reading of the ledger, for either kind it answers for.

    Shared because the SOURCE is the same for both and the clause requires that
    source named: a caller deciding what to retry needs "the ledger" rather than
    whichever of the two verbs happened to be issued.
    """
    return unobservable(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_LEDGER,
        now=now,
        detail=detail,
    )


def _named(*, failure: AttemptFailure) -> str:
    """One expected ledger failure, named by its type and its own message."""
    return f"{type(failure.error).__name__}: {failure.error}"
