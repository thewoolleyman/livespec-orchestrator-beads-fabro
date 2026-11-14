"""Render the governing-only receipt a filing display appends after a taking."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GoverningHeadingReceipt,
    governing_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

__all__: list[str] = ["filing_governing_receipt"]


def filing_governing_receipt(
    *, item_id: str, subject_digest: str, verdict: GoverningHeadingVerdict
) -> str:
    """Render a component receipt that cannot answer as an enclosing verdict.

    The standard marker deliberately makes this receipt visible to the shared
    component reuse reader and invisible to a subject digest.  It omits the
    enclosing ``outcome`` and rubric fields, so ``reusable_verdict`` skips it.
    """
    return "\n".join(
        [
            JUDGEMENT_COMMENT_MARKER,
            "",
            f"work-item: {item_id}",
            *governing_record_lines(
                governing=GoverningHeadingReceipt(verdict=verdict, subject_digest=subject_digest)
            ),
        ]
    )
