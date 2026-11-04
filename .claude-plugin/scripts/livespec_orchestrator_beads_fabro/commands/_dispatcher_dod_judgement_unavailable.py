"""Render the decision and ledger receipt for an unavailable host judgement.

The judgement gate owns taking and reusing a verdict. This module owns the
single unavailable outcome it can return after recording a deduplicated receipt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_decision import (
    DodJudgementDecision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    did_not_run_comment,
    recorded_did_not_run_causes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import SpecIdentity

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["unavailable_decision"]


def unavailable_decision(  # noqa: PLR0913 - each argument is one field of the record it writes.
    *,
    item: WorkItem,
    stage: str,
    digest: str,
    rubric: str,
    judgement: DodJudgement,
    comments: Sequence[str],
    append: Callable[..., None],
    spec_identity: SpecIdentity | None = None,
) -> DodJudgementDecision:
    """Record that the judgement did not run, unless this cause already stands.

    `judgement.cause` is optional because `DodJudgement` carries it only on the
    unavailable outcome; an unavailable verdict with no cause would be a bug in
    the layer above, and recording "it did not run, reason unstated" is worse
    than recording nothing — it is a row an operator cannot act on.

    It returns the DECISION as well as writing, because both of the gate's two
    unavailable arms owe the identical answer and one of them is reached before
    any rubric exists. Two call sites each composing the write and the return was
    how the second arm came to record nothing at all.
    """
    if (cause := judgement.cause) is not None and cause not in recorded_did_not_run_causes(
        comments=comments
    ):
        append(
            body=did_not_run_comment(
                item_id=item.id,
                stage=stage,
                digest=digest,
                rubric_digest=rubric,
                cause=cause,
                bound_ended_candidates=judgement.bound_ended_candidates,
                bound_ended_input_tokens=judgement.bound_ended_input_tokens,
                attempts=judgement.attempts,
                total_input=(judgement.total_input_tokens, judgement.total_input_usage),
            )
        )
    return DodJudgementDecision(
        work_item_id=item.id,
        outcome=JUDGEMENT_UNAVAILABLE,
        spec_identity=spec_identity,
        bound_ended_candidates=judgement.bound_ended_candidates,
        total_input_tokens=judgement.total_input_tokens,
    )
