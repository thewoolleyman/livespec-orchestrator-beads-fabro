"""Which cap triggered a non-convergence bounce, and what that cap observed.

Plan slice S4 (`bd-ib-tbgxm4`) makes the bounce path observable end to end. Two
mechanical signals route a dispatched slice to `backlog`
(`_dispatcher_plan.is_non_convergence_outcome`) and they are different failure
modes: the coarse wall-clock watchdog confirming a run made no progress for its
whole stall window, and the workflow graph's fix-loop visit cap exhausting
through the `non_converged` terminal. A calibration reading that cannot tell
them apart is averaging a hung sandbox with a slice that genuinely would not
converge, and only the second is the "too big" signal the ratified design names
as the reactive ceiling's training signal.

WHY THE OBSERVED VALUE IS ABSENT FOR THE FIX-LOOP CAP, AND PRESENT FOR THE
STALL WINDOW. The watchdog's `decide_stall` confirms a stall ONLY when the
last-event timestamp held unchanged across the FULL window, so the resolved
window IS the quiet duration that was measured at the moment it fired. The
fix-loop visit counter, by contrast, lives inside the sandbox graph: the
`non_converged` terminal prints a fixed sentence and exits, and nothing in the
failed outcome carries the count. Writing the CONFIGURED cap into the observed
field would report a constant as a measurement — an exact round number is the
signature of a configured value and never of an observation, and a record
carrying one is indistinguishable from evidence. So the cap is NAMED and the
observation is recorded as absent. Supplying the per-cycle count is plan slice
S6's work, which is where the commit-series instrument that can measure it
lands.

THE CAP NAMES ARE WHAT AN OPERATOR WOULD TUNE, not internal labels. The stall
window's name is the environment variable its resolver reads, so a bounce record
says which knob moves it; the fix-loop cap's name points at the graph edge that
enforces it.

This module is PURE: the stall window is passed IN by the two callers that
resolve it, so no environment read happens here. That keeps
`_dispatcher_calibration` — which holds this value on its record — a pure
derivation of its inputs.
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
    "STALL_WINDOW_CAP",
    "UNTRIGGERED_NON_CONVERGENCE_CAP",
    "NonConvergenceCap",
    "non_convergence_cap",
]

# The two cap identities, each named as the thing an operator would change. The
# stall window's name is the env var `_dispatcher_watchdog.resolve_stall_seconds`
# reads, so the record points at the knob; the fix-loop cap's name points at the
# `janitor -> fix` visit guard in the workflow graph that enforces it.
STALL_WINDOW_CAP = "LIVESPEC_DISPATCH_STALL_SECONDS"
FIX_LOOP_VISIT_CAP = "workflow.janitor_fix_loop_visit_cap"

# The journal stage the bounce appends, and the two keys the cap rides under.
# One literal each, shared by the producer (`_dispatcher_completion`) and the
# calibration record, exactly as `NON_CONVERGED_MARKER` is shared across its own
# producer and consumer.
NON_CONVERGENCE_BOUNCE_STAGE = "non-convergence-bounce"
BOUNCE_CAP_KEY = "bounce_cap"
BOUNCE_CAP_OBSERVED_KEY = "bounce_cap_observed"

# The watchdog status the engine reports for a confirmed stall
# (`_dispatcher_engine_journal.stalled_outcome`). Tested here rather than
# imported because that module imports the engine, which imports the plan layer
# this module already reads — the constant is one string and the alternative is
# an import cycle.
_STALLED_STATUS = "stalled-no-progress"


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

    `stall_seconds` is the resolved stall window the caller read, which is the
    quiet duration the watchdog measured when it confirmed the stall. It is a
    parameter rather than an environment read so this module stays pure and
    `_dispatcher_calibration` can hold the result without becoming impure.

    The STALL arm is tested before the general predicate because the two arms
    are not mutually exclusive in the predicate's own terms — it answers "is
    this a bounce at all", and a stalled run satisfies it — so a shared ladder
    would report every stall as a fix-loop exhaustion.
    """
    if outcome.status == _STALLED_STATUS:
        return NonConvergenceCap(cap=STALL_WINDOW_CAP, observed=round(stall_seconds))
    if is_non_convergence_outcome(outcome=outcome):
        return NonConvergenceCap(cap=FIX_LOOP_VISIT_CAP, observed=None)
    return UNTRIGGERED_NON_CONVERGENCE_CAP
