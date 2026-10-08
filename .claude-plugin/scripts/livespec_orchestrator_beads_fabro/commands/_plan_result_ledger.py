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
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_LEDGER,
    ResultObservation,
    satisfied,
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


def observe_item_status(
    *, repository: ResultRepository, target: ItemStatusTarget, now: str
) -> ResultObservation | None:
    """Observe whether one ledger item stands at the expected status."""
    config = result_store_config(repository=repository)
    if config is None:
        return None
    read = attempt(
        action=lambda: make_beads_client(config=config).show_issue(issue_id=target.item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    status: object = read.get(_STATUS_FIELD)
    if not isinstance(status, str) or status == "":
        return None
    if status != target.status:
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
        detail=f"the ledger reports {target.item_id} at the expected status {status}",
    )


def observe_item_comment(
    *, repository: ResultRepository, target: ItemCommentTarget, now: str
) -> ResultObservation | None:
    """Observe whether one ledger item carries the exact requested marker."""
    config = result_store_config(repository=repository)
    if config is None:
        return None
    read = attempt(
        action=lambda: read_work_item_comments(path=config, work_item_id=target.item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    comments = tuple(read)
    for position, comment in enumerate(comments, start=1):
        if target.marker not in comment.text:
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
            f"none of the {len(comments)} comment(s) on {target.item_id} carries the"
            f" marker {target.marker!r}"
        ),
    )
