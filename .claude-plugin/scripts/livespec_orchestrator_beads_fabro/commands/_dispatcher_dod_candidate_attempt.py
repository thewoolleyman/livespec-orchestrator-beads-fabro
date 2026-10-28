"""One candidate of the resolved `dod_gate` chain, as a host taking ran it.

`contracts.md` "One rubric, one subject" asks each judgement record to name "for a
chain, each candidate with its outcome". Whether a verdict that a Codex primary
returned also cost an Anthropic request can only be proven from a record that
names the candidates which ran, so every taking carries the list and every
surface that reports a taking renders it through this one module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "CANDIDATE_FIELD",
    "OUTCOME_VERDICT",
    "CandidateAttempt",
    "candidate_record_lines",
]

# The outcome of a candidate whose reply carried a parseable verdict. Every other
# candidate outcome is the cause the chain moved past it with, so a record reads
# `outcome=verdict` for the candidate that decided and a cause for each that did not.
OUTCOME_VERDICT = "verdict"
# One record line per candidate the chain ran, in the order it ran them.
CANDIDATE_FIELD = "candidate"


@dataclass(frozen=True, kw_only=True)
class CandidateAttempt:
    """One candidate of the resolved `dod_gate` chain, as a taking ran it.

    The agent and model are what the candidate RESOLVED to, so a record naming
    `claude-acp` is proof an Anthropic request was made and one naming only
    `codex-acp` is proof none was.
    """

    agent: str
    model: str
    exit_code: int
    outcome: str

    def render(self) -> str:
        """The attempt as one `key=value` line, free of anything a template reads."""
        return (
            f"agent={self.agent} model={self.model} "
            f"exit-code={self.exit_code} outcome={self.outcome}"
        )


def candidate_record_lines(*, attempts: Sequence[CandidateAttempt]) -> list[str]:
    """One `candidate:` record line per attempt, in the order the chain ran them."""
    return [f"{CANDIDATE_FIELD}: {attempt.render()}" for attempt in attempts]
