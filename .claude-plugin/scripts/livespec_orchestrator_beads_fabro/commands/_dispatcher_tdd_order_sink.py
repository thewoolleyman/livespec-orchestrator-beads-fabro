"""Run-scoped host aggregate of the sandbox order guard's decision spans.

Plan `factory-test-first-enforcement` slice S3 (work-item `bd-ib-3h5vfq`)
sources two of the terminal calibration span's seven `tdd.*` fields from slice
S2's shipped decision-event contract: `tdd.order_refusals` and
`tdd.first_product_write_before_red`. The guard
(`.claude/hooks/livespec_tdd_order_guard.py`) POSTs one
`tdd.order.decision` span per PRODUCT-WRITE verdict — allow as well as refuse,
and never for a non-product path — to the live OTLP receiver this sink hangs
off. This module accrues those spans into a small persisted per-dispatch
counter so calibration reads the aggregate out of process, exactly as the cost
gate reads `CostSink` and the telemetry guard reads `RunTurnSink`.

WHY THE KEY IS THE DISPATCH AND NOT THE ITEM. One work-item may be dispatched
many times, and a refusal count is a property of the RUN that earned it. The
guard stamps `work.item.id` and `livespec.dispatch.id` on every decision span
(`livespec_tdd_order_span.correlation_attributes`); both are indexed here, and
`signals_for` reads the FIRST candidate key its caller supplies that has an
entry, so the caller passes the most specific key first. The two keys index
the SAME counter object, so reading either returns one aggregate rather than a
sum that would double-count.

WHY AN UNRECORDED DISPATCH IS `None` AND NOT ZERO. A dropped or never-delivered
signal and a genuinely clean run are the same observation at this seam, and a
zero would report the first as the second — the exact "absent telemetry read as
zero evidence" failure the work-item forbids. So an absent entry is
UNOBSERVABLE, and the calibration record carries `None`, which the analysis
pass treats as missing data.

WHY A BLINDED HEAD STATE FLAGS RATHER THAN CLEARS. `first_product_write_before_red`
is true whenever the first recorded verdict's head state is anything other
than `open-red` — including an unreadable one. This instrument exists to find
post-hoc Red, and a gauge that reads HEALTHY when it cannot observe its input
turns a finding into a pass and leaves a record that looks clean. Note that a
permitted new-module stub carveout therefore sets the flag too: that is
deliberate, because the all-new-module-stubs path is precisely the residual
gap the guard cannot close and this signal exists to make visible (see
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`
section 4.B). The flag is one input to the post-hoc derived column alongside
the gap median, never a verdict on its own.

Posture matches its sibling sinks: every read fails soft to empty, every write
reports success as a bool and never raises, and a `threading.Lock` serializes
the read-modify-write because the receiver serves requests on concurrent
worker threads.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._otel_enrich_tail import IngestedSpan
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "DECISION_SPAN_NAME",
    "HEAD_OPEN_RED",
    "REFUSE_DECISION",
    "TddOrderSignals",
    "TddOrderSink",
    "record_tdd_order_decisions",
]

# The span name, verdict value and head-state value S2 ships. Restated rather
# than imported: `.claude/hooks/` is repo-local dev tooling that is not on the
# shipped plugin's import path, and the plugin must not depend on it. The
# paired test pins each spelling against the shapes the guard emits.
DECISION_SPAN_NAME = "tdd.order.decision"
REFUSE_DECISION = "refuse"
HEAD_OPEN_RED = "open-red"

_DECISION_ATTR = "tdd.decision"
_HEAD_STATE_ATTR = "tdd.head_state"
_CORRELATION_KEYS = ("livespec.dispatch.id", "work.item.id")

_DECISIONS_FIELD = "decisions"
_REFUSALS_FIELD = "refusals"
_FIRST_HEAD_STATE_FIELD = "first_head_state"
_FIRST_AT_FIELD = "first_at"


@dataclass(frozen=True, kw_only=True)
class TddOrderSignals:
    """The two hook-derived TDD order signals for one dispatch.

    Both are `None` together when the dispatch has no recorded decision —
    unobservable, never a clean zero.
    """

    order_refusals: int | None
    first_product_write_before_red: bool | None


@dataclass(kw_only=True)
class TddOrderSink:
    """Persisted `{correlation key -> order-decision counters}` map."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def record_decision(
        self,
        *,
        span: dict[str, object],
        resource_attrs: dict[str, str],
        at: float,
    ) -> bool:
        """Accrue one guard decision span; True iff it was recorded.

        False — recorded nothing — for a span that is not a
        `tdd.order.decision`, for one carrying no correlation key (there is no
        dispatch to attribute it to, and guessing one would credit another
        run's refusals), and for a store the write could not reach.
        """
        if _span_name(span=span) != DECISION_SPAN_NAME:
            return False
        attrs = {**resource_attrs, **_string_attrs(span=span)}
        keys = _correlation_ids(attrs=attrs)
        if not keys:
            return False
        with self._lock:
            stored = self._read()
            entry = _advanced(
                entry=stored.get(keys[0]),
                refused=attrs.get(_DECISION_ATTR) == REFUSE_DECISION,
                head_state=attrs.get(_HEAD_STATE_ATTR, ""),
                at=at,
            )
            for key in keys:
                stored[key] = entry
            return self._write(stored=stored)

    def signals_for(self, *, keys: tuple[str, ...]) -> TddOrderSignals:
        """The order signals for the first supplied key that has an entry.

        `keys` is most-specific-first (the dispatch id before the work-item
        id). A key with no entry falls through to the next; none matching
        yields the fully-unobservable pair.
        """
        with self._lock:
            stored = self._read()
        for key in keys:
            entry = stored.get(key)
            if key != "" and entry is not None:
                return TddOrderSignals(
                    order_refusals=_int_field(entry=entry, name=_REFUSALS_FIELD),
                    first_product_write_before_red=(
                        entry.get(_FIRST_HEAD_STATE_FIELD) != HEAD_OPEN_RED
                    ),
                )
        return TddOrderSignals(order_refusals=None, first_product_write_before_red=None)

    def _read(self) -> dict[str, dict[str, object]]:
        """The persisted map, or empty for any store that cannot be read.

        There is deliberately NO `is_file()` pre-check: a missing store, a
        store that is a directory, and an unreadable one are all the same
        answer here — empty — and one `attempt` covers them without a second
        probe that could disagree with the read that follows it.
        """
        stored = attempt(
            action=lambda: self.path.read_text(encoding="utf-8"), exceptions=(OSError,)
        )
        if isinstance(stored, AttemptFailure):
            return {}
        raw = parse_json(text=stored)
        if isinstance(raw, JsonParseFailure) or not isinstance(raw, dict):
            return {}
        entries: dict[str, dict[str, object]] = {}
        for key, value in cast("dict[str, object]", raw).items():
            if isinstance(value, dict):
                entries[scrub(value=key)] = cast("dict[str, object]", value)
        return entries

    def _write(self, *, stored: dict[str, dict[str, object]]) -> bool:
        text = json.dumps(stored, separators=(",", ":"), sort_keys=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        written = attempt(
            action=lambda: _write_atomic(path=self.path, tmp=tmp, text=text),
            exceptions=(OSError,),
        )
        return not isinstance(written, AttemptFailure)


def record_tdd_order_decisions(
    *,
    sink: TddOrderSink | None,
    spans: tuple[IngestedSpan, ...],
    at: float,
) -> int:
    """Accrue every order-decision span in one ingest batch; count recorded.

    `sink=None` is the unwired case (a receiver built without the sink) and is
    a successful no-op returning 0, mirroring how the receiver treats an
    unwired cost sink.
    """
    if sink is None:
        return 0
    return sum(
        1
        for ingested in spans
        if sink.record_decision(span=ingested.span, resource_attrs=ingested.resource_attrs, at=at)
    )


def _advanced(
    *,
    entry: dict[str, object] | None,
    refused: bool,
    head_state: str,
    at: float,
) -> dict[str, object]:
    """The counter object after one more decision.

    The first-write head state and instant are written only when ABSENT, so
    the recorded first verdict stays the first one observed for this dispatch
    rather than being overwritten by each later decision.
    """
    existing = entry or {}
    first_head_state = existing.get(_FIRST_HEAD_STATE_FIELD)
    return {
        _DECISIONS_FIELD: (_int_field(entry=existing, name=_DECISIONS_FIELD) or 0) + 1,
        _REFUSALS_FIELD: (_int_field(entry=existing, name=_REFUSALS_FIELD) or 0)
        + (1 if refused else 0),
        _FIRST_HEAD_STATE_FIELD: (
            first_head_state if isinstance(first_head_state, str) else head_state
        ),
        _FIRST_AT_FIELD: existing.get(_FIRST_AT_FIELD, at),
    }


def _int_field(*, entry: dict[str, object], name: str) -> int:
    """One counter field as an int; 0 for an absent or non-int stored value."""
    value = entry.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _span_name(*, span: dict[str, object]) -> str:
    raw = span.get("name")
    return raw if isinstance(raw, str) else ""


def _correlation_ids(*, attrs: dict[str, str]) -> tuple[str, ...]:
    """The correlation keys this decision carries, most specific first."""
    return tuple(scrub(value=attrs[key]) for key in _CORRELATION_KEYS if attrs.get(key, "") != "")


def _string_attrs(*, span: dict[str, object]) -> dict[str, str]:
    """The span's string-valued attributes; a malformed entry is skipped.

    One odd entry must not blind the whole span: the guard's five verdict keys
    and the two correlation keys are read independently, so an unreadable
    `tdd.decision` still leaves the correlation usable.
    """
    raw_attrs = span.get("attributes")
    if not isinstance(raw_attrs, list):
        return {}
    attrs: dict[str, str] = {}
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        value = entry.get("value")
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            attrs[key] = string_value
    return attrs


def _write_atomic(*, path: Path, tmp: Path, text: str) -> None:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    _ = tmp.write_text(text, encoding="utf-8")
    _ = tmp.replace(path)
