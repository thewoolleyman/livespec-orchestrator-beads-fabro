"""Read-only Definition-of-Done verdict lookup for drains and hygiene."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    RecordedJudgement,
    recorded_governing_heading,
    reusable_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    spec_identity_for_governing,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["held_judgement", "item_comment_bodies"]


def item_comment_bodies(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...] | None:
    """Read an item's comments oldest-first, or ``None`` when its sidecar is unavailable."""
    read = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=work_item_id),
        exceptions=(
            BeadsCommandError,
            BeadsConnectionError,
            BeadsMappingError,
            BeadsTenantMissingError,
        ),
    )
    return None if isinstance(read, AttemptFailure) else tuple(comment.text for comment in read)


def held_judgement(
    *, item: WorkItem, repo: Path, comments: Sequence[str], payload_root: Path | None = None
) -> RecordedJudgement | None:
    """Return a standing refusal without taking a governing-heading judgement."""
    rubric = judgement_rubric(payload_root=payload_root)
    if rubric is None:
        return None
    identity = spec_identity_for_governing(
        item=item,
        cwd=repo,
        governing=recorded_governing_heading(comments=comments),
    )
    recorded = reusable_verdict(
        comments=comments,
        digest=judgement_subject_digest(
            item=item, cwd=repo, comments=comments, spec_identity=identity.value
        ),
        rubric_digest=rubric_digest(rubric=rubric),
    )
    return recorded if recorded is not None and recorded.outcome == JUDGEMENT_HELD else None
