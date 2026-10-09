"""The two agreeing projections of one dispatch's runtime cycle observations.

Plan slice S6 (`bd-ib-z2y4ca`). `SPECIFICATION/contracts.md` requires the
terminal calibration journal and span to "expose the per-cycle observations or
explicit absence diagnostics, effective assertion count, completed-cycle count,
and whether a progress deficit or adopted cycle ceiling contributed to the
bounce", and then — in the sentence that makes this module exist — "their
projections MUST agree: absent numeric observations remain null in the journal
and omitted numeric attributes on the span, with an accompanying reason".

SO THE TWO SHAPES ARE DERIVED FROM ONE SOURCE, NOT WRITTEN TWICE. Both
projections below are built from the same `_fields` mapping, so a key cannot be
added to one surface and forgotten on the other, and the two cannot disagree
about a VALUE at all. What they are allowed to differ in is exactly one thing:
how they spell an absence.

HOW EACH SURFACE SPELLS AN ABSENCE, AND WHY THEY DIFFER. The JOURNAL keeps an
explicit `null`, which is the honest record of having looked and found nothing.
The SPAN omits the attribute, for the two reasons `_dispatcher_tdd_signals`
already records for its own fields: the egress encoder would otherwise ship the
literal string `"None"`, and a numeric column that sometimes holds `"None"`
cannot be compared numerically by a derived column. Neither surface substitutes
a zero.

AND THE REASON TRAVELS WITH THE ABSENCE ON BOTH. An omitted span attribute is
indistinguishable from a signal nobody tried to measure unless the reason is
there beside it, so the `*_unobserved_reason` keys are STRINGS and are present on
the span exactly when their numeric sibling is missing. That is what the clause's
"with an accompanying reason" buys, and it is the half most easily dropped,
because the numeric omission alone already looks tidy.

WHY THE PER-CYCLE OBSERVATIONS RIDE AS ONE JSON STRING ON THE SPAN. OTLP
attributes are scalars, and the cycles are a list of records. The journal carries
them structurally; the span carries the same list serialized once, under one
attribute, so an operator can read a run's cycles out of Honeycomb without a new
service and without one attribute per cycle per field. The COUNT and the
contributors are separate scalar attributes precisely so the queryable facts stay
queryable.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    CompletedCycle,
    CompletedCycleSeries,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_convergence import (
    RuntimeConvergenceVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    PRODUCT_LLOC_MEASUREMENT_METHOD,
)

__all__: list[str] = [
    "CYCLE_PROJECTED_KEYS",
    "cycle_journal_fields",
    "cycle_observations",
    "cycle_span_fields",
]

_CYCLES_KEY = "cycle_observations"
_COMPLETED_COUNT_KEY = "completed_cycle_count"
_ASSERTION_COUNT_KEY = "effective_assertion_count"
_CONTRIBUTORS_KEY = "bounce_contributors"
_SERIES_UNOBSERVED_KEY = "cycle_series_unobserved_reason"
_PROGRESS_UNOBSERVED_KEY = "cycle_progress_unobserved_reason"
_MEASUREMENT_METHOD_KEY = "cycle_measurement_method"

# Declared ONCE, in projection order, for the reason `TDD_PROJECTED_KEYS` is:
# every consumer — the journal record, the span attributes, the allowlist
# assertion — reads the key set from here.
CYCLE_PROJECTED_KEYS: tuple[str, ...] = (
    _CYCLES_KEY,
    _COMPLETED_COUNT_KEY,
    _ASSERTION_COUNT_KEY,
    _CONTRIBUTORS_KEY,
    _SERIES_UNOBSERVED_KEY,
    _PROGRESS_UNOBSERVED_KEY,
    _MEASUREMENT_METHOD_KEY,
)


def cycle_observations(*, cycles: tuple[CompletedCycle, ...]) -> list[dict[str, object | None]]:
    """The per-cycle observations, one record each, absences as explicit nulls.

    The ordinal, pair identity and commit are always present — they are what the
    clause means by retaining "source identities and measurement method … for
    operator replay" — while each measurement is either its number or a null
    beside the reason it could not be taken.
    """
    return [
        {
            "ordinal": cycle.ordinal,
            "pair_id": cycle.pair_id,
            "commit": cycle.commit,
            "product_lloc_changed": cycle.product_lloc_changed,
            "product_lloc_unobserved_reason": cycle.product_lloc_unobserved_reason,
            "elapsed_seconds": cycle.elapsed_seconds,
            "elapsed_unobserved_reason": cycle.elapsed_unobserved_reason,
        }
        for cycle in cycles
    ]


def cycle_journal_fields(
    *, series: CompletedCycleSeries, verdict: RuntimeConvergenceVerdict
) -> dict[str, object | None]:
    """Every projected key, including the absent ones — the JOURNAL shape."""
    return dict(_fields(series=series, verdict=verdict))


def cycle_span_fields(
    *, series: CompletedCycleSeries, verdict: RuntimeConvergenceVerdict
) -> dict[str, object]:
    """Only the OBSERVED keys, with the cycles serialized — the SPAN shape.

    An absent attribute is the correct OTLP representation of an unobservable
    signal; the reason keys beside it are strings and survive, which is what
    keeps an omission readable rather than merely tidy.
    """
    fields = _fields(series=series, verdict=verdict)
    projected: dict[str, object] = {}
    for key, value in fields.items():
        if value is None:
            continue
        projected[key] = json.dumps(value) if key == _CYCLES_KEY else value
    return projected


def _fields(
    *, series: CompletedCycleSeries, verdict: RuntimeConvergenceVerdict
) -> dict[str, object | None]:
    """The ONE source both projections are built from.

    `cycle_observations` is `None` — not an empty list — for an UNREADABLE
    series, because an empty list is the honest record of a run that authored no
    cycle and the two must not collapse. The count beside it carries the same
    distinction, and the reason says which case this is.
    """
    return {
        _CYCLES_KEY: None if not series.observed else cycle_observations(cycles=series.cycles),
        _COMPLETED_COUNT_KEY: series.completed_count,
        _ASSERTION_COUNT_KEY: series.assertion_count,
        _CONTRIBUTORS_KEY: list(verdict.contributors),
        _SERIES_UNOBSERVED_KEY: series.unreadable_reason,
        _PROGRESS_UNOBSERVED_KEY: verdict.progress_unobserved_reason,
        _MEASUREMENT_METHOD_KEY: PRODUCT_LLOC_MEASUREMENT_METHOD,
    }
