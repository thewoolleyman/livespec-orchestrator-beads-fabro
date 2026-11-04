"""Render the ledger record for a Definition-of-Done judgement that did not run."""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    CandidateAttempt,
    unavailable_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_input_record import (
    bound_ended_lines,
    total_input_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    UNAVAILABLE_COMMENT_MARKER,
)


def did_not_run_comment(  # noqa: PLR0913 - each argument is one record field.
    *,
    item_id: str,
    stage: str,
    digest: str,
    rubric_digest: str,
    cause: str,
    bound_ended_candidates: Sequence[str] = (),
    bound_ended_input_tokens: Sequence[int | None] = (),
    attempts: Sequence[CandidateAttempt] = (),
    total_input: tuple[int | None, str] = (None, "unreported"),
) -> str:
    """Render the ledger comment for one unavailable host judgement."""
    return "\n".join(
        (
            UNAVAILABLE_COMMENT_MARKER,
            "",
            f"The {stage} Definition-of-Done judgement did not run for this item.",
            "",
            f"work-item: {item_id}",
            f"stage: {stage}",
            f"outcome: {JUDGEMENT_UNAVAILABLE}",
            f"subject-digest: {digest}",
            f"rubric-digest: {rubric_digest}",
            f"judgement-unavailable-cause: {cause}",
            *total_input_lines(
                total_tokens=total_input[0],
                usage=total_input[1],
                input_limited=cause == "input-limit-reached",
            ),
            *bound_ended_lines(
                candidates=bound_ended_candidates,
                input_tokens=bound_ended_input_tokens,
            ),
            *unavailable_record_lines(attempts=attempts),
        )
    )
