"""What the per-cycle observations contribute to the non-convergence bounce.

Plan slice S6 (`bd-ib-z2y4ca`). `SPECIFICATION/contracts.md` adds TWO runtime
convergence conditions on top of the existing ones, and this module is the pure
decision both evaluation points share — the pre-merge convergence verification
boundary and the terminal non-converged recording.

THE PROGRESS CONDITION IS BOUND TO THE CAP, AND THAT BINDING IS THE RULE. "At
the existing configured fix-loop cap, an observed completed-cycle count below
the effective assertion count MUST contribute to the sanctioned non-convergence
return to `backlog`, surfacing both counts and the cap" — and in the same breath,
"this comparison MUST NOT cause an earlier count-only bounce, alter the cap, or
treat sufficient count as proof of acceptance". So `at_fix_loop_cap` is a
parameter rather than something inferred here: a run that is three assertions
into a five-assertion item is MID-WORK, and bouncing it would convert an
ordinary in-progress dispatch into a re-groom.

INCLUDING WHEN ACCEPTANCE PASSES AT THE CAP. The clause says the condition
applies "including when ordinary acceptance first passes on the cap-th allowed
attempt: the progress gate is an additional convergence condition at that
boundary". The verdict is therefore a function of the MEASUREMENTS and the cap
alone, and knows nothing about the acceptance result — it cannot be waived by a
pass it never reads. The mirror also holds: "sufficient count as proof of
acceptance" is impossible here because a sufficient count produces NO verdict at
all, leaving the ordinary gates to decide on their own.

WHY UNOBSERVED IS ITS OWN FIELD RATHER THAN A FALSE DEFICIT. "If the series or
assertion count cannot be established, the progress comparison MUST be reported
unobserved rather than as a zero-count deficit; existing non-convergence still
applies." An unreadable series has no count, and `None < 3` is not a comparison —
so the two unestablished cases set `progress_unobserved_reason` and leave
`progress_deficit` false. The ordinary cap-based non-convergence is untouched
either way, because this verdict only ever ADDS a contributor.

WHY THE CEILING CONDITION IS NOT BOUND TO THE CAP. A breach is a measurement
about ONE cycle, not about the run's convergence over time, and the clause puts
its evaluation at "its pre-merge convergence verification boundary and when
recording a terminal non-converged run" — before the cap is necessarily reached.
So a breach contributes on its own, which is why `cap` and `cap_value` are
optional here.

AND WHY NOTHING ABOUT THE ITEM REACHES THIS FUNCTION. "The intake
`size_justification` exception MUST NOT waive these independent runtime gates."
The strongest way to hold that is for the work-item not to be an input at all:
a justification cannot waive a gate that never reads one. The same reasoning
excludes the acceptance verdict above.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    CompletedCycleSeries,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    AdoptedCycleCeilings,
    CycleCeilingBreach,
    cycle_ceiling_breaches,
)

__all__: list[str] = [
    "CYCLE_CEILING_CONTRIBUTOR",
    "PROGRESS_DEFICIT_CONTRIBUTOR",
    "UNOBSERVED_ASSERTION_COUNT",
    "RuntimeConvergenceVerdict",
    "runtime_convergence_verdict",
]

# The two contributor names the journal and the span expose, spelled once. They
# are NAMES of conditions rather than numbered reasons, so a record says which
# gate fired instead of leaving a reader to map an ordinal onto a clause.
PROGRESS_DEFICIT_CONTRIBUTOR = "completed-cycle-deficit"
CYCLE_CEILING_CONTRIBUTOR = "adopted-cycle-ceiling"

# Why a progress comparison could not be made when the SERIES was fine: the
# dispatched criteria yielded no gradeable assertion count. Distinct from the
# series' own unreadable reason because the remedy is different — one is a probe
# to fix, the other is an item whose criteria nothing can grade.
UNOBSERVED_ASSERTION_COUNT = "assertion-count-unestablished"


@dataclass(frozen=True, kw_only=True)
class RuntimeConvergenceVerdict:
    """The runtime convergence reading at one evaluation boundary.

    Carries every figure the bounce must surface rather than a boolean, because
    the clause requires the record to name "both counts and the cap" and the
    breach to name its setting, limit, measurement and cycle identity — a
    verdict reduced to "bounce" would force each surface to re-derive them.
    """

    at_fix_loop_cap: bool
    cap: str | None
    cap_value: int | None
    completed_count: int | None
    assertion_count: int | None
    progress_deficit: bool
    progress_unobserved_reason: str | None
    breaches: tuple[CycleCeilingBreach, ...]

    @property
    def contributors(self) -> tuple[str, ...]:
        """The named conditions that contribute to a bounce, in clause order."""
        found: list[str] = []
        if self.progress_deficit:
            found.append(PROGRESS_DEFICIT_CONTRIBUTOR)
        if self.breaches:
            found.append(CYCLE_CEILING_CONTRIBUTOR)
        return tuple(found)

    @property
    def bounces(self) -> bool:
        """Whether this reading contributes a non-convergence bounce at all."""
        return bool(self.contributors)

    def as_reason(self) -> str | None:
        """The surfaced reason, or None when nothing contributed.

        `None` rather than an empty string, so a caller cannot journal a reason
        that reads as a finding on a run where no runtime gate fired.
        """
        clauses: list[str] = []
        if self.progress_deficit:
            observed = f"observed {self.completed_count} completed Red-Green cycle(s)"
            against = f"against {self.assertion_count} effective assertion(s)"
            boundary = f"at the configured fix-loop cap {self.cap} = {self.cap_value}"
            clauses.append(f"{observed} {against} {boundary}")
        clauses.extend(breach.as_reason() for breach in self.breaches)
        return "; ".join(clauses) if clauses else None


def runtime_convergence_verdict(
    *,
    series: CompletedCycleSeries,
    ceilings: AdoptedCycleCeilings,
    at_fix_loop_cap: bool,
    cap: str | None,
    cap_value: int | None,
) -> RuntimeConvergenceVerdict:
    """Read the runtime convergence conditions at one evaluation boundary.

    `at_fix_loop_cap` is resolved by the caller from what it can OBSERVE of the
    dispatch's own fix loops, because the workflow graph's visit counter lives
    inside the sandbox and no terminal carries it — the limitation
    `_dispatcher_non_convergence_cap` already records.
    """
    completed = series.completed_count
    assertions = series.assertion_count
    unobserved = _progress_unobserved_reason(series=series, at_fix_loop_cap=at_fix_loop_cap)
    deficit = (
        at_fix_loop_cap
        and unobserved is None
        and completed is not None
        and assertions is not None
        and completed < assertions
    )
    return RuntimeConvergenceVerdict(
        at_fix_loop_cap=at_fix_loop_cap,
        cap=cap,
        cap_value=cap_value,
        completed_count=completed,
        assertion_count=assertions,
        progress_deficit=deficit,
        progress_unobserved_reason=unobserved,
        breaches=cycle_ceiling_breaches(series=series, ceilings=ceilings),
    )


def _progress_unobserved_reason(
    *, series: CompletedCycleSeries, at_fix_loop_cap: bool
) -> str | None:
    """Why the progress comparison could not be made, or None when it could.

    Only reported AT the cap: before it the comparison is deliberately not being
    made, so recording it as unobservable would file a diagnostic about a reading
    nobody asked for — and that diagnostic would appear on every healthy
    mid-flight dispatch.
    """
    if not at_fix_loop_cap:
        return None
    if not series.observed:
        return series.unreadable_reason
    if series.assertion_count is None:
        return UNOBSERVED_ASSERTION_COUNT
    return None
