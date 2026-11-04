"""Which ledger comments are the Dispatcher's own Definition-of-Done receipts.

ONE question, asked by three unrelated surfaces: the judgement SUBJECT, which
carries every rider and no receipt; the node's rendered GOAL, which carries the
same set for the same reason; and the record reader, which tells a verdict from
a did-not-run record.

WHY IT IS A LEAF OF ITS OWN. `_dispatcher_dod_judgement_record` owns the record
FORMAT, and it imports the judgement value type to render one — so the two
surfaces that only need the question would have to pull that whole import
closure in to ask it, and `_dispatcher_goal` would acquire a dependency on the
criteria resolution to render a brief. Worse, the natural alternative is for each
surface to spell the marker itself, and a marker spelled twice is two answers to
"is this comment a receipt": the subject would carry a receipt the goal omitted,
and the item's digest would then move every time a verdict was recorded.

WHY THE MARKER IS THE WHOLE DISCRIMINATOR, AND WHY IT IS THE FIRST LINE. A
receipt is the Dispatcher's own write and an operator rider is prose, so nothing
inside the body can separate them reliably — a rider quoting a verdict is an
ordinary rider, and this repository's own items carry several. The first
non-blank line is a marker the Dispatcher controls and an operator has no reason
to open a comment with.
"""

from __future__ import annotations

__all__: list[str] = [
    "JUDGEMENT_COMMENT_MARKER",
    "UNAVAILABLE_COMMENT_MARKER",
    "comment_marker",
    "is_judgement_record",
    "is_receipt_comment",
]

# The first line of each record, and the whole of how a reader tells these
# comments from the operator riders beside them.
JUDGEMENT_COMMENT_MARKER = "livespec-dod-judgement"
UNAVAILABLE_COMMENT_MARKER = "livespec-dod-judgement-unavailable"

_RECORD_MARKERS = frozenset({JUDGEMENT_COMMENT_MARKER, UNAVAILABLE_COMMENT_MARKER})

# The filing-time records that are receipts, not brief: each reports a judgement
# taken against ONE specification version, so a later revision can supersede it
# and a judge handed it as a rider grades the superseded verdict. The tier marker
# is matched by EXACT first line (its `-unavailable` extension is a different
# record); a mechanical finding is matched by the prefix filing writes before it.
_SPEC_CHANGE_TIER_MARKER = "livespec-spec-change-tier"
_MECHANICAL_FINDING_PREFIX = "definition-of-done finding (mechanical):"


def comment_marker(*, body: str) -> str:
    """One comment's first non-blank line, or the empty string for a blank one."""
    return body.strip().partition("\n")[0].strip()


def is_judgement_record(*, body: str) -> bool:
    """Whether one comment is a Dispatcher Definition-of-Done judgement receipt.

    EXACT equality on the marker line, never a prefix test. The unavailable
    marker extends the verdict marker, so a `startswith` reading would be true
    for both under either name — which is fine here but is one edit away from
    reading an operator comment opening `livespec-dod-judgement-is-wrong` as a
    receipt, and a receipt is the one class of comment the subject drops.
    """
    return comment_marker(body=body) in _RECORD_MARKERS


def is_receipt_comment(*, body: str) -> bool:
    """Whether one comment is a receipt the subject and the goal both leave out.

    A judgement receipt, a spec-change tier record, or a filing-time mechanical
    finding comment. Any other comment is an operator rider. Omitting a comment
    here never removes it from the ledger: needs-attention and the filer read it.
    """
    marker = comment_marker(body=body)
    return (
        is_judgement_record(body=body)
        or marker == _SPEC_CHANGE_TIER_MARKER
        or marker.startswith(_MECHANICAL_FINDING_PREFIX)
    )
