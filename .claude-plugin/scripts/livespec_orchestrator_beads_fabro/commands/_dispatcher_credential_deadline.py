"""What a credential must cover, and the ABSOLUTE instant its use must stop.

TWO FIGURES, ONE DERIVATION, AND THE RELATION BETWEEN THEM IS THE WHOLE POINT.

`CredentialLifetimeRequirement` carries the resolved workflow's execution
ALLOWANCE and the documented safety MARGIN. The dispatch freshness gate demands
their sum; the worker's credential-use DEADLINE is the allowance alone, measured
from the instant the credential was projected. A credential admitted by the gate
therefore outlives the deadline by at least the margin, which is what makes the
deadline a bound the credential can always reach rather than one it might expire
before.

WHY AN ALLOWANCE IS NOT ENOUGH ON ITS OWN, and why this module exists rather
than a bare integer. A sum of separately-bounded sub-operations is not a
deadline anything enforces -- `_dispatcher_execution_budget` says so in as many
words about the figure it derives, and the gap is real. Read first-hand from the
pinned engine at 8869e88b2f7e383ec6fceb8d3f6f928dd0339b34: `fabro-core`'s
executor takes a `retry_target` jump when a terminal is reached with a goal gate
unsatisfied, and that jump is not a DOT edge, so no graph parse can see it;
`fabro-sandbox` spends the checkpoint budget independently on `git add`, on
`git diff --cached` and on `git commit`; `fabro-workflow` resolves artifact
context outside the handler timeout a derivation multiplies. Every one of those
makes a derived maximum SMALLER than the run can be, and announces nothing.

So the allowance is turned into something enforced: an ABSOLUTE epoch instant,
projected into the sandbox, which the worker's own launch guard measures itself
against. That is what closes the gap -- not a tighter derivation, but an actor
that stops execution at a named instant. The allowance alone would be an
estimate relabelled a maximum, which is exactly the move the governing ruling
forbids.

WHY THE CLOCK STARTS AT PROJECTION. The credential is read, graded and projected
into the run configuration BEFORE the run is submitted, so a deadline measured
from the first node's start would exclude the queue and preparation delay -- the
interval that ages a projected credential most, and the one a worker-start
refusal exists to catch. Anchoring at projection makes that delay count AGAINST
the budget instead of silently extending it, and it is also what makes the
deadline survive a retry: a relaunched node recomputes its remaining time from
the same instant, so nothing resets.

WHY THE ARITHMETIC LIVES HERE AND NOT AT ITS CALL SITES. Three surfaces ask
these questions -- the host gate before the claim, the overlay at projection,
and the in-sandbox guard at every node launch -- and they must agree exactly.
Two of them are on opposite sides of a container boundary, so a disagreement
would present as a credential that the host admitted and the worker refused,
with nothing in either record to show which arithmetic was wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CredentialLifetimeRequirement",
    "credential_use_deadline_epoch",
    "credential_use_remaining_seconds",
]


@dataclass(frozen=True, kw_only=True)
class CredentialLifetimeRequirement:
    """One workflow's resolved credential requirement, with the evidence for it.

    `detail` is carried rather than rebuilt by each consumer because it names
    the CONFIGURATION behind the figure -- which workflow, which allowance,
    which per-attempt overhead -- and an operator told only a number has no
    route back to the keys that produced it.
    """

    allowance_seconds: int
    margin_seconds: int
    detail: str

    @property
    def required_seconds(self) -> int:
        """The usable lifetime the freshness gate demands of a credential.

        The margin sits ON TOP of the allowance rather than inside it: the
        allowance bounds credential USE, and the margin is the separation
        between a rotation and the work depending on it. Folding the margin
        into the allowance would move the enforced deadline too, spending the
        separation on execution instead of keeping it as headroom.
        """
        return self.allowance_seconds + self.margin_seconds


def credential_use_deadline_epoch(*, projected_epoch: int, allowance_seconds: int) -> int:
    """The absolute instant after which a worker may not use the credential.

    The ALLOWANCE, not the requirement: the margin is headroom between the
    deadline and the credential's own expiry, so spending it as execution time
    would leave a run authenticating on its last second.
    """
    return projected_epoch + allowance_seconds


def credential_use_remaining_seconds(*, deadline_epoch: int, now_epoch: int) -> int:
    """How much credential-use budget is left, on the clock of whoever asks.

    NEGATIVE OR ZERO IS A REAL ANSWER and is deliberately not clamped. The
    in-sandbox guard needs to tell "no budget left" from "a little left", and a
    value floored at zero makes a deadline that passed during a long queue
    indistinguishable from one reached exactly now. Every caller compares
    against zero rather than treating this as a duration.
    """
    return deadline_epoch - now_epoch
