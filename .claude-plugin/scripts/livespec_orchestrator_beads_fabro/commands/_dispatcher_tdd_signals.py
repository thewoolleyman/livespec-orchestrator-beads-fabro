"""The terminal calibration span's TDD order projection.

Plan `factory-test-first-enforcement` slice S3 (work-item `bd-ib-3h5vfq`) puts
SEVEN `tdd.*` fields (slice S6 has since added two verified-pair fields) on every
terminal `dispatcher.calibration` span, plus the
implement node's adapter as the second dimension the Honeycomb board groups
by. This module is the one place that names those keys and assembles their
values from the three derivations that own them.

SOURCE SEMANTICS, field by field — this list is the documented contract the
work-item's first Definition-of-Done assertion requires, and the honest answer
to "what does this number mean" for each:

- `tdd.red_commit_count` — commits in THIS dispatch's series carrying
  `TDD-Red-Captured-At`. A Green-amended commit retains both trailer sets and
  counts once here and once as a Green, so a completed cycle reads 1/1, not
  2/1. Source: `_dispatcher_tdd_commits`.
- `tdd.green_commit_count` — commits carrying `TDD-Green-Verified-At`. Red
  minus Green is the count of Reds left open at the end of the run.
- `tdd.suite_green_count` — commits carrying `TDD-Suite-Green-Captured-At`,
  the `red_green_replay` leg-5 shape: product code with NO Red at all. Counted
  separately from Green so a no-Red commit is never reported as a completed
  cycle.
- `tdd.red_green_gap_seconds_median` — the median interval between a commit's
  Red and Green trailer instants, in WHOLE SECONDS (the derivation is exact
  and is rounded here, because the egress encoder ships a float as a string
  and a string column cannot be compared numerically by a derived column).
  This is the load-bearing number: genuine test-first work spends the
  implementation time inside that interval, while producing the commit shape
  after the fact spends seconds in it.
- `tdd.first_product_write_before_red` — whether the FIRST product-write
  verdict the sandbox order guard recorded for this dispatch happened while
  HEAD was not an open Red. A permitted new-module stub carveout sets it too,
  by design: that is the residual gap the guard cannot close, and this flag is
  what makes it visible. Source: `_dispatcher_tdd_order_sink`.
- `tdd.order_refusals` — how many product writes the guard REFUSED during
  this dispatch. Source: the same sink, keyed per dispatch.
- `tdd.assertion_count` — the number of gradeable assertions in the item's
  EFFECTIVE acceptance criteria, through `effective_criteria` — the exact
  segmentation the acceptance evaluator grades and the operator sees at filing
  time. It was deliberately NOT the sibling `acceptance_count`, which counted
  bullet and Gherkin markers in the DESCRIPTION and read zero on most items;
  slice S4 (`bd-ib-tbgxm4`) has since repaired that field to the same parser,
  and both now read `_dispatcher_assertion_count` so the two cannot diverge
  again.
- `tdd.verified_pair_count` — the number of DISTINCT verified Red-Green pairs
  in THIS dispatch's series (Scenario 165, plan slice S6 part one): commits
  carrying BOTH the Red and the Green trailer, de-duplicated on the Red's own
  evidence, so a Green amendment, a duplicate observation, an open Red, a
  suite-green-only commit and another run's history each add nothing. `0` is
  an OBSERVED empty series; it is the one place a zero is projected, and only
  for a series that was read. Source: `_dispatcher_completed_cycles`.
- `tdd.verified_pair_unobserved_reason` — why that count is absent, when the
  series could not be read (`no-pull-request`, `no-dispatch-id`,
  `commits-unreadable`, `series-not-identified`). Set exactly when the count
  is not.
- `livespec.implement.adapter` — the registry agent id of the implement
  node's resolved ACP adapter. Source: `_dispatcher_implement_adapter`.

WHY `None` IS PROJECTED DIFFERENTLY ON THE TWO SURFACES. Every field is
`None` when its underlying signal was not observable for this dispatch — a
non-merged run has no commit series to read, and a dispatch whose guard spans
never arrived has no order aggregate. The JOURNAL keeps the explicit null,
because a JSON null is the honest record of having looked and found nothing.
The SPAN omits the attribute entirely, for two reasons: the egress encoder
would otherwise ship the literal string `"None"`, and a numeric column that
sometimes holds `"None"` is unqueryable. An omitted attribute reads as absent
in Honeycomb, which is what it is. Neither surface ever substitutes a zero —
a zero gap and zero refusals are precisely the healthy-looking reading a
dropped signal would fabricate.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count import (
    assertion_count_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    VerifiedPairCount,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import TddCommitSignals
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSignals
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "IMPLEMENT_ADAPTER_KEY",
    "IMPLEMENT_SELECTED_INDEX_KEY",
    "TDD_PROJECTED_KEYS",
    "UNOBSERVED_TDD_SIGNALS",
    "TddSignals",
    "assertion_count",
    "tdd_signal_fields",
    "tdd_signals",
    "tdd_span_fields",
    "with_verified_pairs",
]

_RED_COMMIT_COUNT_KEY = "tdd.red_commit_count"
_GREEN_COMMIT_COUNT_KEY = "tdd.green_commit_count"
_SUITE_GREEN_COUNT_KEY = "tdd.suite_green_count"
_GAP_SECONDS_MEDIAN_KEY = "tdd.red_green_gap_seconds_median"
_FIRST_WRITE_BEFORE_RED_KEY = "tdd.first_product_write_before_red"
_ORDER_REFUSALS_KEY = "tdd.order_refusals"
_ASSERTION_COUNT_KEY = "tdd.assertion_count"
_VERIFIED_PAIR_COUNT_KEY = "tdd.verified_pair_count"
_VERIFIED_PAIR_REASON_KEY = "tdd.verified_pair_unobserved_reason"

# The adapter is NOT a `tdd.*` key: it is a grouping dimension of the dispatch,
# not a test-first measurement, and naming it `tdd.adapter` would misreport
# what it describes.
IMPLEMENT_ADAPTER_KEY = "livespec.implement.adapter"
IMPLEMENT_SELECTED_INDEX_KEY = "livespec.implement.selected_index"

# Declared ONCE, in projection order. Every consumer — the journal record, the
# span attributes, the allowlist assertion, the Honeycomb definitions — reads
# the key set from here, so a key cannot be added to one surface and forgotten
# on another.
TDD_PROJECTED_KEYS: tuple[str, ...] = (
    _RED_COMMIT_COUNT_KEY,
    _GREEN_COMMIT_COUNT_KEY,
    _SUITE_GREEN_COUNT_KEY,
    _GAP_SECONDS_MEDIAN_KEY,
    _FIRST_WRITE_BEFORE_RED_KEY,
    _ORDER_REFUSALS_KEY,
    _ASSERTION_COUNT_KEY,
    _VERIFIED_PAIR_COUNT_KEY,
    _VERIFIED_PAIR_REASON_KEY,
    IMPLEMENT_ADAPTER_KEY,
)


@dataclass(frozen=True, kw_only=True)
class TddSignals:
    """One dispatch's TDD order signals, each `None` when unobservable.

    Every field defaults to absent so `UNOBSERVED_TDD_SIGNALS` is the whole
    unobserved record rather than eight repeated `None` arguments, and so a
    dispatch path that has not been wired to supply them reports absence
    rather than a plausible zero.
    """

    red_commit_count: int | None = None
    green_commit_count: int | None = None
    suite_green_count: int | None = None
    red_green_gap_seconds_median: int | None = None
    first_product_write_before_red: bool | None = None
    order_refusals: int | None = None
    assertion_count: int | None = None
    verified_pair_count: int | None = None
    verified_pair_unobserved_reason: str | None = None
    adapter: str | None = None
    selected_index: int | None = None
    size_justified: bool | None = None


# The fully-unobserved record. It is the default on `CalibrationRecord`, so an
# entry point that does not gather these signals journals explicit nulls.
UNOBSERVED_TDD_SIGNALS = TddSignals()


def tdd_signals(
    *,
    item: WorkItem,
    commits: TddCommitSignals | None,
    order: TddOrderSignals,
    adapter: str | None,
    selected_index: int | None = None,
    size_justified: bool | None = None,
) -> TddSignals:
    """Assemble one dispatch's TDD signals from the three derivations.

    `commits=None` is a dispatch with no readable commit series (a run that
    never merged, or a `gh` probe that could not answer), and leaves all four
    commit fields absent rather than zero. `order` always arrives — the sink
    reports its own absence as `None` fields — and `adapter` is `None` when no
    node resolution was journaled for the item.
    The verified-pair count is NOT assembled here: it is applied afterwards by
    `with_verified_pairs`, so a path that never read the series leaves the
    count AND its reason absent rather than manufacturing either.
    """
    return TddSignals(
        red_commit_count=None if commits is None else commits.red_commit_count,
        green_commit_count=None if commits is None else commits.green_commit_count,
        suite_green_count=None if commits is None else commits.suite_green_count,
        red_green_gap_seconds_median=_whole_seconds(
            value=None if commits is None else commits.red_green_gap_seconds_median
        ),
        first_product_write_before_red=order.first_product_write_before_red,
        order_refusals=order.order_refusals,
        assertion_count=assertion_count(item=item),
        adapter=adapter,
        selected_index=selected_index,
        size_justified=size_justified,
    )


def with_verified_pairs(*, signals: TddSignals, pairs: VerifiedPairCount) -> TddSignals:
    """These signals carrying one dispatch's verified-pair count and its reason."""
    return replace(
        signals,
        verified_pair_count=pairs.count,
        verified_pair_unobserved_reason=pairs.unobserved_reason,
    )


def assertion_count(*, item: WorkItem) -> int:
    """The item's gradeable assertion count, through the sanctioned parser.

    `effective_criteria` resolves the SAME source and segmentation the
    acceptance evaluator grades — the description's Definition of Done
    section, else the criteria field, else the description's exit criteria —
    so this number is the one an operator already sees at filing time rather
    than a second, differently-wrong count.

    It reaches that parser through `_dispatcher_assertion_count`, the shared
    projection plan slice S4 (`bd-ib-tbgxm4`) adopted once the legacy
    `acceptance_count` beside it was repaired to the same number: two fields on
    one span reporting different counts of the same thing is exactly what S4
    retired, and it would have returned had each kept its own resolution.
    """
    return assertion_count_for(item=item).count


def tdd_signal_fields(*, signals: TddSignals) -> dict[str, object | None]:
    """Every projected key, including the absent ones — the JOURNAL shape.

    A `None` here is recorded as a JSON null, which is the honest record of
    "observed, nothing there". Key ORDER follows `TDD_PROJECTED_KEYS`.
    """
    return {
        _RED_COMMIT_COUNT_KEY: signals.red_commit_count,
        _GREEN_COMMIT_COUNT_KEY: signals.green_commit_count,
        _SUITE_GREEN_COUNT_KEY: signals.suite_green_count,
        _GAP_SECONDS_MEDIAN_KEY: signals.red_green_gap_seconds_median,
        _FIRST_WRITE_BEFORE_RED_KEY: signals.first_product_write_before_red,
        _ORDER_REFUSALS_KEY: signals.order_refusals,
        _ASSERTION_COUNT_KEY: signals.assertion_count,
        _VERIFIED_PAIR_COUNT_KEY: signals.verified_pair_count,
        _VERIFIED_PAIR_REASON_KEY: signals.verified_pair_unobserved_reason,
        IMPLEMENT_ADAPTER_KEY: signals.adapter,
    }


def tdd_span_fields(*, signals: TddSignals) -> dict[str, object]:
    """Only the OBSERVED keys — the SPAN shape.

    An absent attribute is the correct OTLP representation of an unobservable
    signal. The alternative the egress encoder would produce is the literal
    string `"None"` in a column the derived column compares numerically, which
    is worse than silence because it reads as data.
    """
    return {
        key: value for key, value in tdd_signal_fields(signals=signals).items() if value is not None
    }


def _whole_seconds(*, value: float | None) -> int | None:
    """Round an exact gap median to whole seconds, preserving absence.

    Absence survives rounding: `None` in, `None` out. Rounding an unobservable
    median to `0` would read as the sharpest possible post-hoc signal.
    """
    return None if value is None else round(value)
