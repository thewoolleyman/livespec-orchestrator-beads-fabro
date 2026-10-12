"""WHICH stage's failure routed a run to the needs-human terminal, if any did.

`_fabro_escalation` answers whether the ENGINE routed a run to the terminal at
all; `_fabro_terminal_evidence` reads the terminal checkpoint's own fields. This
module is the DECISION between the three endings those fields can describe, and
it is separate because the rendering needs a single verdict while the evidence
needs to stay unjudged.

THE THREE ENDINGS, AND WHY NONE OF THEM MAY BE THE DEFAULT:

- `STAGE_FAILURE` — a node is recorded failed in the terminal checkpoint's own
  outcome map. There is a stage to name and no question to answer.
- `AGENT_REQUEST` — the outcome map WAS read and records no failed predecessor,
  so an agent rode a conditional edge off a node that succeeded. A question
  genuinely awaits a human.
- `UNESTABLISHED` — the record cannot ground either answer: no terminal
  checkpoint was readable, or one was but its outcome map was not. Nothing is
  attributed and nothing is denied.

The third arm is the one that keeps the other two honest. `AGENT_REQUEST` used
to be reached by SILENCE — no loop failure signature meant "an agent asked" —
and that inference fails in BOTH directions on measured records. A
provider-ceiling run records an explicit failed `implement` outcome with no loop
signature at all, so silence reported a question for a run that never asked; and
the engine never clears a loop signature when a later visit to the same node
succeeds, so a run that recovered and THEN asked still carried a signature that
would be attributed as its cause. Reading an absence as a positive finding
produced both, so `AGENT_REQUEST` now requires the positive evidence of a READ
outcome map, and a record supplying none lands in `UNESTABLISHED` rather than
being assigned the more convenient of the two.

HISTORY IS CARRIED BESIDE THE VERDICT, NEVER FOLDED INTO IT. A loop signature
belonging to a stage that is not currently failed is real evidence about the
run and no evidence about this ending. Dropping it loses the run's account;
attributing it invents a cause. It travels as `history` so a renderer can say
which it is.

Every surviving stage is carried rather than only the newest: more than one
node CAN fail in a single loop, and naming one of several hides the rest behind
an answer that looks complete.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import TerminalEvidence

__all__: list[str] = [
    "AGENT_REQUEST",
    "STAGE_FAILURE",
    "UNESTABLISHED",
    "CausalStageFailure",
    "causal_stage_failure",
]

STAGE_FAILURE = "stage-failure"
AGENT_REQUEST = "agent-request"
UNESTABLISHED = "unestablished"


@dataclass(frozen=True, kw_only=True)
class CausalStageFailure:
    """One verdict about why a run reached the needs-human terminal.

    `stages` and `signatures` are populated only for `STAGE_FAILURE`; `history`
    can be populated under any kind, because a run can carry outlived failures
    whatever its ending turned out to be.
    """

    kind: str
    stages: tuple[str, ...]
    signatures: tuple[str, ...]
    history: tuple[str, ...]

    @property
    def is_stage_failure(self) -> bool:
        """Whether a recorded stage failure caused this ending — the fault arm."""
        return self.kind == STAGE_FAILURE


def causal_stage_failure(*, evidence: TerminalEvidence | None) -> CausalStageFailure:
    """Decide between the three endings one terminal's evidence can describe.

    A verdict is ALWAYS returned, including for absent evidence. Returning
    `None` for "nothing established" is what let an unreadable record share an
    arm with a genuine question: both reached one renderer, which then had to
    tell a single story about two opposite situations.
    """
    if evidence is None:
        return CausalStageFailure(kind=UNESTABLISHED, stages=(), signatures=(), history=())
    if evidence.failed_stages:
        return CausalStageFailure(
            kind=STAGE_FAILURE,
            stages=evidence.failed_stages,
            signatures=evidence.stage_signatures,
            history=evidence.history_signatures,
        )
    return CausalStageFailure(
        kind=AGENT_REQUEST if evidence.outcomes_observed else UNESTABLISHED,
        stages=(),
        signatures=(),
        history=evidence.history_signatures,
    )
