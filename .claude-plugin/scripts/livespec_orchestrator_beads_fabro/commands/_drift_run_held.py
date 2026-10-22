"""Held-finding records on the detection-coverage anchor.

The THIRD record type the anchor carries, beside the attempt and completed
records `_detection_coverage` owns. The detection coverage-record contract
admits it by name: appending "the drift run's held-finding records" to the
designated anchor is inside the self-bookkeeping exception, and nothing else.

A HELD FINDING IS NOT A DISPOSED ONE, and that is the whole reason this record
exists rather than the finding simply being dropped. The contract says a held
finding "is NOT disposed", that the frontier "MUST NOT advance past a merge
with a held finding", and that `needs-attention` MUST list held findings with a
handoff naming `revise`. All three need the identity to SURVIVE the pass: the
run that held it ends, the root timer fires again ten minutes later, and
without a durable record the next pass would re-derive the same finding with no
way to know it had already been held — so it would hold it again, and the
operator surface would list one finding once per tick.

⛔ EVERY WRITE HERE NAMES THE ANCHOR AND NOTHING ELSE, which is what keeps the
self-bookkeeping exception honest and is checkable by reading this file: the
client seam is reached exactly twice, once for `add_comment` and once (through
`read_work_item_comments`) for the read-back, and both name `anchor`.

AN UNCONFIGURED ANCHOR CANNOT HOLD, and `record_held_finding` says so by
answering False rather than by raising or by quietly succeeding. A finding
nobody could hold is a finding this pass has not disposed of, so the frontier
must stop at its merge — which is exactly what the pass does with a False. A
write that pretended to succeed would advance the frontier over a finding that
exists nowhere.

THE READ IS FAIL-SOFT, exactly as `completed_coverage_point`'s is and for the
same reason: it runs inside the needs-attention composition, where letting a
committed anchor id that names no live row escape would take the whole
attention snapshot down for one wrong config value. Answering an empty tuple
there under-reports held findings, which is the direction that leaves the
operator with fewer facts rather than none at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "HELD_MARKER_PREFIX",
    "HeldFinding",
    "held_findings",
    "record_held_finding",
]

HELD_MARKER_PREFIX = "livespec-drift-held-finding: "

_IDENTITY_FIELD = "identity"
_MERGE_FIELD = "merge"
_KIND_FIELD = "kind"
_TARGET_FIELD = "generalization_target"


@dataclass(frozen=True, kw_only=True)
class HeldFinding:
    """One finding held past the queue cap, as its anchor record describes it.

    Carries the MERGE as well as the identity, because the operator reading the
    needs-attention listing has to know which merge is holding the frontier,
    and the identity alone is a digest that names no commit.
    """

    identity: str
    merge: str
    kind: str
    generalization_target: str | None


def record_held_finding(
    *, path: StoreConfig | None, anchor: str | None, finding: DriftFinding
) -> bool:
    """Append ONE held-finding record to the anchor; False when it could not be.

    False is the fail-CLOSED answer an unconfigured anchor — or a repository
    whose connection block does not resolve to a tenant at all — earns, and the
    pass reads it as "this finding is not held", which stops the frontier at its
    merge. See the module docstring for why a silent success there would be the
    expensive direction.

    BOTH inputs are optional for one reason: a hold needs a tenant to write to
    AND a row to write on, and a repository missing either cannot hold. Taking
    only the anchor would make a repository with no resolvable connection raise
    from inside the disposition of one finding, which kills the whole pass over
    a question that has a perfectly good answer.
    """
    if path is None or anchor is None or anchor.strip() == "":
        return False
    body = HELD_MARKER_PREFIX + json.dumps(
        {
            _IDENTITY_FIELD: finding.identity,
            _MERGE_FIELD: finding.merge,
            _KIND_FIELD: finding.kind,
            _TARGET_FIELD: finding.generalization_target,
        },
        sort_keys=True,
    )
    make_beads_client(config=path).add_comment(issue_id=anchor, body=body)
    return True


def held_findings(*, path: StoreConfig | None, anchor: str | None) -> tuple[HeldFinding, ...]:
    """Every held finding on record, oldest first, deduplicated by identity.

    An unresolvable connection answers an empty tuple, exactly as an unreadable
    anchor does: in both cases no hold can be read, and raising here would take
    down the needs-attention composition this read runs inside.

    Deduplicated because the record is append-only and a build that held one
    finding twice — or an operator who re-ran a pass against an anchor written
    by an older build — must not make the operator surface list it twice. The
    FIRST record of an identity wins, so the hold's own first observation is
    what is reported.
    """
    if path is None:
        return ()
    resolved = path
    comments = attempt(
        action=lambda: read_work_item_comments(path=resolved, work_item_id=anchor or ""),
        exceptions=(BeadsMappingError,),
    )
    if isinstance(comments, AttemptFailure):
        return ()
    found: dict[str, HeldFinding] = {}
    for comment in comments:
        if not comment.text.startswith(HELD_MARKER_PREFIX):
            continue
        one = _decode(payload=comment.text.removeprefix(HELD_MARKER_PREFIX))
        if one is not None and one.identity not in found:
            found[one.identity] = one
    return tuple(found.values())


def _decode(*, payload: str) -> HeldFinding | None:
    """One held-finding record, or None when its payload will not read as one.

    Fail-soft per record, mirroring `read_work_item_comments`: a comment whose
    payload does not parse is skipped rather than blinding the read of every
    other hold on the anchor.
    """
    parsed = parse_json(text=payload)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    identity = fields.get(_IDENTITY_FIELD)
    merge = fields.get(_MERGE_FIELD)
    kind = fields.get(_KIND_FIELD)
    target = fields.get(_TARGET_FIELD)
    if not isinstance(identity, str) or not isinstance(merge, str) or not isinstance(kind, str):
        return None
    return HeldFinding(
        identity=identity,
        merge=merge,
        kind=kind,
        generalization_target=target if isinstance(target, str) else None,
    )
