"""The judgement-free read of a standing Definition-of-Done refusal."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    RecordedJudgement,
    reusable_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    spec_identity_for_governing,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["held_judgement"]


def held_judgement(
    *, item: WorkItem, repo: Path, comments: tuple[str, ...], payload_root: Path | None = None
) -> RecordedJudgement | None:
    """Return the standing refusal without taking or recording a judgement."""
    rubric = judgement_rubric(payload_root=payload_root)
    if rubric is None:
        return None
    governing = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    identity = spec_identity_for_governing(item=item, cwd=repo, governing=governing)
    recorded = reusable_verdict(
        comments=comments,
        digest=judgement_subject_digest(
            item=item, cwd=repo, comments=comments, spec_identity=identity.value
        ),
        rubric_digest=rubric_digest(rubric=rubric),
    )
    if recorded is None or recorded.outcome != JUDGEMENT_HELD:
        return None
    return recorded
