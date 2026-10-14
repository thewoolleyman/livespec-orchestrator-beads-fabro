"""Which cap triggered a non-convergence bounce, and what that cap observed.

Plan slice S4 (`bd-ib-tbgxm4`) makes the bounce path observable end to end. ONE
mechanical signal routes a dispatched slice to `backlog`
(`_dispatcher_plan.is_non_convergence_outcome`): the workflow graph's fix-loop
visit cap exhausting through the `non_converged` terminal. That is the "too
big" signal the ratified design names as the reactive ceiling's training
signal.

THE WATCHDOG'S STALL WINDOW IS DELIBERATELY NOT A CAP HERE, and the module's
own earlier docstring is why it needed naming: it warned that a calibration
reading which cannot tell a hung sandbox from a slice that genuinely would not
converge is averaging two unrelated failure modes — and then classified both,
which made the two distinguishable on the record while leaving them identical
in disposition. `contracts.md`'s "Dispatcher progress watchdog" settles it:
a `stalled-no-progress` outcome "is NOT factory non-convergence", the
Dispatcher must journal no `non-convergence-bounce` record for it, and "the
calibration analysis pass MUST NOT count it as a non-convergence observation".
So a stall classifies as `UNTRIGGERED_NON_CONVERGENCE_CAP` (`bd-ib-nfbyot`).
Nothing an operator needs is lost: the resolved window, the layer that supplied
it and the quiet duration actually confirmed all ride the
`watchdog-stall-cancel` record the cancel itself journals, which is where a
cancellation's own figures belong.

WHY THE OBSERVED VALUE IS ABSENT FOR THE FIX-LOOP CAP. The fix-loop visit
counter lives inside the sandbox graph: the `non_converged` terminal prints a
fixed sentence and exits, and nothing in the failed outcome carries the count.
Writing the CONFIGURED cap into the observed field would report a constant as a
measurement — an exact round number is the signature of a configured value and
never of an observation, and a record carrying one is indistinguishable from
evidence. So the cap is NAMED and the observation is recorded as absent.
Supplying the per-cycle count is plan slice S6's work, which is where the
commit-series instrument that can measure it lands.

THE CAP NAME IS WHAT AN OPERATOR WOULD TUNE, not an internal label: the
fix-loop cap's name points at the `janitor -> fix` visit guard in the workflow
graph that enforces it.

This module is PURE: the stall window is still passed IN by the two callers
that resolve it, so no configuration read happens here. It is retained as a
parameter rather than dropped because `decide_stall`'s window is the figure a
future cap could be graded against, and because both callers already hold it;
what changed is that no arm reports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    is_non_convergence_outcome,
)

__all__: list[str] = [
    "BOUNCE_CAP_KEY",
    "BOUNCE_CAP_OBSERVED_KEY",
    "FIX_LOOP_VISIT_CAP",
    "NON_CONVERGENCE_BOUNCE_STAGE",
    "UNTRIGGERED_NON_CONVERGENCE_CAP",
    "NonConvergenceCap",
    "non_convergence_cap",
]

# The one cap identity a bounce can name, spelled as the thing an operator
# would change: the `janitor -> fix` visit guard in the workflow graph.
#
# `STALL_WINDOW_CAP` stood beside it until `bd-ib-nfbyot`, naming the committed
# key `dispatcher.stall_timeout_seconds`. That key is still the knob that moves
# the watchdog window and `_dispatcher_stall_window` still resolves it; what it
# is no longer is a NON-CONVERGENCE cap, so the name lives with the cancel
# record rather than here.
FIX_LOOP_VISIT_CAP = "workflow.janitor_fix_loop_visit_cap"

# The journal stage the bounce appends, and the two keys the cap rides under.
# One literal each, shared by the producer (`_dispatcher_completion`) and the
# calibration record, exactly as `NON_CONVERGED_MARKER` is shared across its own
# producer and consumer.
NON_CONVERGENCE_BOUNCE_STAGE = "non-convergence-bounce"
BOUNCE_CAP_KEY = "bounce_cap"
BOUNCE_CAP_OBSERVED_KEY = "bounce_cap_observed"


class _TerminalOutcome(Protocol):
    """Structural view of the two fields the classification reads.

    The same shape `is_non_convergence_outcome` reads, and for the same reason:
    a concrete `DispatchOutcome` import would be circular, and these two fields
    are all the decision needs.
    """

    @property
    def status(self) -> str: ...

    @property
    def detail(self) -> str: ...


@dataclass(frozen=True, kw_only=True)
class NonConvergenceCap:
    """The cap a non-convergence bounce tripped, and the value it observed.

    `cap` is `None` for a terminal that is not a non-convergence bounce at all,
    which is every green run and every ordinary failure. `observed` is `None`
    whenever the triggering cap carries no measurement — see the module
    docstring for why that is recorded as absence rather than as the configured
    cap value.
    """

    cap: str | None
    observed: int | None

    def as_record(self) -> dict[str, object | None]:
        """The two flat sibling keys, for the journal and the calibration span.

        Flat rather than nested for the reason every calibration field is: the
        OTLP enrich stage promotes a sibling key straight to a span attribute,
        and a nested map would have to be unwrapped by a stage that does not.
        """
        return {BOUNCE_CAP_KEY: self.cap, BOUNCE_CAP_OBSERVED_KEY: self.observed}


# The value for a terminal that tripped no cap. It is the default on
# `CalibrationRecord`, so a dispatch path that does not resolve the cap journals
# explicit nulls rather than a plausible one.
UNTRIGGERED_NON_CONVERGENCE_CAP = NonConvergenceCap(cap=None, observed=None)


def non_convergence_cap(*, outcome: _TerminalOutcome, stall_seconds: float) -> NonConvergenceCap:
    """Classify one terminal outcome's non-convergence cap.

    `stall_seconds` is the resolved stall window the caller read. It is a
    parameter rather than an environment read so this module stays pure and
    `_dispatcher_calibration` can hold the result without becoming impure. No
    arm reports it since `bd-ib-nfbyot` ruled a watchdog stall out of
    non-convergence; see the module docstring for why the parameter is kept.

    The classification asks the SAME predicate the bounce itself asks, which is
    the point rather than a tidiness: a cap derived separately from the
    transition it describes can disagree with it, and the disagreement is
    invisible because both surfaces look correct on their own. That is also why
    a stall needs no arm of its own here — the predicate already declines it,
    so the cap and the bounce decline together by construction.
    """
    _ = stall_seconds
    if is_non_convergence_outcome(outcome=outcome):
        return NonConvergenceCap(cap=FIX_LOOP_VISIT_CAP, observed=None)
    return UNTRIGGERED_NON_CONVERGENCE_CAP
