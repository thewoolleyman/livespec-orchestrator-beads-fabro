"""The value a host Definition-of-Done taking returns to its caller.

This is separate from the gate because the decision is shared output: the gate
decides whether to reuse, take, and record a verdict, while callers need the
same small receipt to route the item and journal its candidate and input size.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    first_remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import SpecIdentity

__all__: list[str] = ["DodJudgementDecision"]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDecision:
    """What one call site learned, including the input evidence it must journal."""

    work_item_id: str
    outcome: str
    findings: tuple[str, ...] = ()
    reused: bool = False
    spec_identity: SpecIdentity | None = None
    deciding_candidate: str | None = None
    bound_ended_candidates: tuple[str, ...] = ()
    total_input_tokens: int | None = None

    @property
    def holds(self) -> bool:
        """Whether this decision rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def first_remedy(self) -> str | None:
        """The remedy a refusal and a hygiene fact name."""
        return first_remedy(findings=self.findings)
