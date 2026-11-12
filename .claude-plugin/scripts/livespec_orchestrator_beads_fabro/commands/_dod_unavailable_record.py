"""The did-not-run receipt for a Definition-of-Done judgement.

This is separate from the taken-verdict record because a taking that cannot run
has no verdict to render. It owns the unavailable marker and the record fields
that explain the interruption, including input-bound subject measurements.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from typing_extensions import Unpack

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    CandidateAttempt,
    unavailable_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_input_record import (
    bound_ended_lines,
    input_bound_detail_lines,
    total_input_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    UNAVAILABLE_COMMENT_MARKER,
)

__all__: list[str] = [
    "STAGE_PRE_ADMISSION",
    "STAGE_PRE_DISPATCH",
    "did_not_run_comment",
]

STAGE_PRE_ADMISSION = "pre-admission"
STAGE_PRE_DISPATCH = "pre-dispatch"

_WORK_ITEM_FIELD = "work-item"
_STAGE_FIELD = "stage"
_OUTCOME_FIELD = "outcome"
_DIGEST_FIELD = "subject-digest"
_RUBRIC_DIGEST_FIELD = "rubric-digest"
_CAUSE_FIELD = "judgement-unavailable-cause"
_FIELD_SEPARATOR = ": "


class _DidNotRunDetails(TypedDict, total=False):
    subject_characters: int | None
    carried_rider_count: int | None
    bound_ended_candidates: Sequence[str]
    bound_ended_input_tokens: Sequence[int | None]
    attempts: Sequence[CandidateAttempt]
    total_input: tuple[int | None, str]


def did_not_run_comment(
    *,
    item_id: str,
    stage: str,
    digest: str,
    rubric_digest: str,
    cause: str,
    **details: Unpack[_DidNotRunDetails],
) -> str:
    """Render a ledger receipt stating why the judgement did not run."""
    return "\n".join(
        (
            UNAVAILABLE_COMMENT_MARKER,
            "",
            f"The {stage} Definition-of-Done judgement did not run for this item.",
            "",
            f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item_id}",
            f"{_STAGE_FIELD}{_FIELD_SEPARATOR}{stage}",
            f"{_OUTCOME_FIELD}{_FIELD_SEPARATOR}{JUDGEMENT_UNAVAILABLE}",
            f"{_DIGEST_FIELD}{_FIELD_SEPARATOR}{digest}",
            f"{_RUBRIC_DIGEST_FIELD}{_FIELD_SEPARATOR}{rubric_digest}",
            f"{_CAUSE_FIELD}{_FIELD_SEPARATOR}{cause}",
            *input_bound_detail_lines(
                cause=cause,
                subject_characters=details.get("subject_characters"),
                carried_rider_count=details.get("carried_rider_count"),
            ),
            *total_input_lines(
                total_tokens=details.get("total_input", (None, "unreported"))[0],
                usage=details.get("total_input", (None, "unreported"))[1],
                input_limited=cause == "input-limit-reached",
            ),
            *bound_ended_lines(
                candidates=details.get("bound_ended_candidates", ()),
                input_tokens=details.get("bound_ended_input_tokens", ()),
            ),
            *unavailable_record_lines(attempts=details.get("attempts", ())),
        )
    )
