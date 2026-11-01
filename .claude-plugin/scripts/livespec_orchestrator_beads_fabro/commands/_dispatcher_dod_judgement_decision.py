"""The shared result shape of one Definition-of-Done judgement taking."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    BoundEndedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    first_remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SpecIdentity,
)

__all__: list[str] = ["DodJudgementDecision"]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDecision:
    """What one call site learned, and whether anything was spent learning it."""

    work_item_id: str
    outcome: str
    findings: tuple[str, ...] = ()
    reused: bool = False
    spec_identity: SpecIdentity | None = None
    deciding_candidate: str | None = None
    input_tokens: int | None = None
    bound_ended_candidates: tuple[str | BoundEndedCandidate, ...] = ()

    @property
    def holds(self) -> bool:
        """Whether this decision rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def first_remedy(self) -> str | None:
        """The remedy a refusal and a hygiene fact name."""
        return first_remedy(findings=self.findings)
