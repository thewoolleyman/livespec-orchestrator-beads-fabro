"""What one Definition-of-Done judgement call site learned.

Split out of the gate, which sits at the file size ceiling, and unchanged in
behaviour: the gate composes the decision and every caller reads it from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    first_remedy,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
        SpecIdentity,
    )

__all__: list[str] = ["DodJudgementDecision"]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDecision:
    """What one call site learned, and whether anything was spent learning it.

    `reused` is reported rather than inferred from `findings`, because a reused
    verdict and a freshly-taken identical one are indistinguishable by outcome —
    and the two caps the clause states are about the SPEND, not the answer.
    """

    work_item_id: str
    outcome: str
    findings: tuple[str, ...] = ()
    reused: bool = False
    spec_identity: SpecIdentity | None = None

    @property
    def holds(self) -> bool:
        """Whether this decision rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def first_remedy(self) -> str | None:
        """The remedy a refusal and a hygiene fact name."""
        return first_remedy(findings=self.findings)
