"""Host-local OTLP enrich/scrub stage — the 29f pipeline data plane (E1).

The CORE new artifact of the 29f telemetry leg, per
`loop-reflection-gate/telemetry-pipeline-architecture.md` §3
(the RECOMMENDATION in §3.2: a custom host-local OTLP processor, a small
stdlib-first Python service, NOT an off-the-shelf otelcol collector). This
module is the AUGMENT + SCRUB chokepoint between the local span files the
dispatcher + 29f.2 reflection stage write and Honeycomb:

  [dispatcher / reflection local span files] ──▶ enrich/scrub stage ──▶ Honeycomb
                                                  (correlation triple,
                                                   fail-closed scrub,
                                                   batch + retry egress)

Three jobs (all decided by the doc, no design fork):

1. **File-tail ingest** (§3.2 (b)). The dispatcher + reflection stage write
   `<journal-stem>-reflection-spans.jsonl` in the canonical OTLP/HTTP-JSON
   one-`ExportTraceServiceRequest`-per-line shape. `tail_spans` reads the
   appended lines past a byte offset (a resumable cursor), parses each into
   its constituent spans + the per-line resource, and returns them. A
   missing file / malformed line is skipped fail-open (a forward error
   never blocks a dispatch — the dispatcher already wrote the authoritative
   journal).

2. **Correlation-triple augmentation** (§3.3). The stage holds a small
   in-memory map keyed on `work.item.id` and `fabro.run_id`, populated as
   dispatcher spans arrive. When a CC / fabro span carries ONE key of the
   triple, `CorrelationJoin` backfills the others as span attributes before
   forwarding, so the reflector joins on ONE key set (`GROUP BY work.item.id`)
   regardless of source.

3. **Fail-CLOSED credential scrub on EVERY forwarded span** (§3.4). Every
   span passes through the SHARED `_otel_scrub` discipline (allowlist, not
   denylist; reject-not-redact on a credential shape) before egress. A span
   whose scrub drops a value entirely is still forwarded with the value
   redacted — but a span carrying a credential-shaped value in an
   allowlisted attribute is REJECTED (dropped) so a scrub miss fails closed.

Egress (§3.5): batch + retry to Honeycomb via the ingest-only key
`HONEYCOMB_INGEST_KEY_LIVESPEC` (OTLP/HTTP → https://api.honeycomb.io,
header `x-honeycomb-team`, dataset derived from `service.name`). The HTTP
poster is an INJECTABLE `SpanExporter` Protocol seam so the stage is
fully unit-testable WITHOUT a real network call: tests inject a fake
exporter; the real `HoneycombHttpExporter` uses stdlib `urllib` (no new
dependency — stdlib-first per the family discipline) with bounded retry.

Posture (§3.2): **fail-OPEN toward the pipeline** — a forward / export
error never raises out of `forward_once` and never blocks a dispatch — but
**fail-CLOSED toward credentials** — a credential-shaped match drops the
span rather than risk leaking. Same dual posture as the 29f.2 reflection
stage.

DEFERRED to follow-up children (a correct first increment beats a wrong
monolith): the live OTLP/HTTP RECEIVER (the bound port the sandbox ships
to — a network-listening daemon + its dispatcher supervision is a
framework fork the doc leaves open) and the metrics-heartbeat low-latency
forward path (§4.4, depends on the receiver + metrics ingest shape). This
module is the file-tail + correlation + scrub + batch-egress data plane
those build on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._otel_enrich_export import (
    HoneycombHttpExporter,
    SpanExporter,
    honeycomb_dataset_for,
)
from livespec_orchestrator_beads_fabro.commands._otel_enrich_tail import (
    IngestedSpan,
    TailResult,
    tail_spans,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    REDACTION_MARKER,
    attr,
    is_allowed_attr,
    scrub,
)

__all__: list[str] = [
    "CorrelationJoin",
    "EnrichStage",
    "ForwardResult",
    "HoneycombHttpExporter",
    "IngestedSpan",
    "SpanExporter",
    "TailResult",
    "correlation_keys_from_attrs",
    "enrich_span",
    "honeycomb_dataset_for",
    "tail_spans",
]

# The correlation triple keys (§3.3) — the uniform key set the reflector
# joins on. `work.item.id` is the join-map key; the other two are backfilled.
_WORK_ITEM_ID = "work.item.id"
_DISPATCH_ID = "livespec.dispatch.id"
_FABRO_RUN_ID = "fabro.run_id"
_DISPATCH_FACTORY = "livespec.dispatch.factory"
_DISPATCH_CONTEXT_KEYS = (_WORK_ITEM_ID, _DISPATCH_ID, _FABRO_RUN_ID, _DISPATCH_FACTORY)


@dataclass(frozen=True, kw_only=True)
class ForwardResult:
    """The outcome of one `forward_once` pass (fail-open: never raises)."""

    ingested: int
    forwarded: int
    rejected: int
    exported: bool
    offset: int


@dataclass(kw_only=True)
class CorrelationJoin:
    """In-memory join map keyed on `work.item.id` and `fabro.run_id` (§3.3).

    Populated as dispatcher spans arrive (they carry the full triple);
    when a CC / fabro span later carries ONE key of the triple, the stage
    backfills the others. The map is process-scoped state (a mutable
    holder, not module globals) so the stage updates it without a `global`
    statement — matching the `_AutoTripState` pattern in
    `_dispatcher_reflection`.
    """

    _by_work_item: dict[str, dict[str, str]] = field(default_factory=dict)
    _by_fabro_run: dict[str, dict[str, str]] = field(default_factory=dict)

    def observe(self, *, keys: dict[str, str]) -> None:
        """Record the triple values a span carries.

        Learns from a span carrying EITHER anchor — `work.item.id`, the
        primary join key, or `fabro.run_id`. The second anchor is what makes
        a Petri-era span teachable: that engine stamps `fabro.run_id` as a
        plain attribute on every span and emits none of the 0.254 run-id
        events, and its spans reach the receiver with no orchestrator span
        beside them, so a map anchored on `work.item.id` alone learned
        nothing from a whole run. A span carrying neither anchor cannot be
        placed and is ignored. Each newly-seen triple key is merged in (later
        spans backfill earlier gaps without clobbering a known value).
        """
        known = self._anchor(keys=keys)
        if known is None:
            return
        for triple_key in _DISPATCH_CONTEXT_KEYS:
            value = keys.get(triple_key)
            if value is not None and triple_key not in known:
                known[triple_key] = value
        fabro_run = known.get(_FABRO_RUN_ID)
        if fabro_run is not None:
            _ = self._by_fabro_run.setdefault(fabro_run, known)

    def _anchor(self, *, keys: dict[str, str]) -> dict[str, str] | None:
        """The ONE triple record both indexes reach for this span's anchors.

        Spans arrive in no guaranteed order, so a run first seen by
        `fabro.run_id` and later by `work.item.id` must land on the SAME
        record: a fresh dict per index would leave two half-triples for one
        run, each answering its own lookup and neither answering the other.
        """
        work_item = keys.get(_WORK_ITEM_ID)
        fabro_run = keys.get(_FABRO_RUN_ID)
        if work_item is not None:
            known = self._by_work_item.get(work_item)
            if known is None and fabro_run is not None:
                known = self._by_fabro_run.get(fabro_run)
            if known is None:
                known = {}
            self._by_work_item[work_item] = known
            return known
        if fabro_run is not None:
            return self._by_fabro_run.setdefault(fabro_run, {})
        return None

    def backfill(self, *, keys: dict[str, str]) -> dict[str, str]:
        """Return the triple values to stamp on a span, backfilling from the map.

        Starts from the keys the span already carries (those win) and adds
        any missing triple member known for its `work.item.id`; a span with
        no `work.item.id` can still backfill from a known `fabro.run_id`.
        Unknown keys get only what they brought.
        """
        result = {k: v for k, v in keys.items() if k in _DISPATCH_CONTEXT_KEYS}
        work_item = result.get(_WORK_ITEM_ID)
        if work_item is not None:
            known = self._by_work_item.get(work_item, {})
        else:
            fabro_run = result.get(_FABRO_RUN_ID)
            known = self._by_fabro_run.get(fabro_run, {}) if fabro_run is not None else {}
        for triple_key, value in known.items():
            _ = result.setdefault(triple_key, value)
        return result


def correlation_keys_from_attrs(*, span: dict[str, object]) -> dict[str, str]:
    """Extract the correlation-triple key/values a span already carries.

    Reads the span's OTLP `attributes` list and the Fabro run-id span
    events nested under `events[]`, returning only string-valued
    correlation keys. Span attributes use the normalized triple names and
    win over event-derived values; Fabro events use raw `run_id` / `id`
    names and are normalized to `fabro.run_id` before stamping.
    """
    found: dict[str, str] = {}
    _collect_span_correlation_attrs(found=found, raw_attrs=span.get("attributes"))
    if _FABRO_RUN_ID not in found:
        run_id = _fabro_run_id_from_events(raw_events=span.get("events"))
        if run_id is not None:
            found[_FABRO_RUN_ID] = run_id
    return found


def _collect_span_correlation_attrs(*, found: dict[str, str], raw_attrs: object) -> None:
    if not isinstance(raw_attrs, list):
        return
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if not isinstance(key, str) or key not in _DISPATCH_CONTEXT_KEYS:
            continue
        string_value = _string_attr_value(entry=entry)
        if string_value is not None:
            found[key] = string_value


def _fabro_run_id_from_events(*, raw_events: object) -> str | None:
    if not isinstance(raw_events, list):
        return None
    fallback_id: str | None = None
    for raw_event in cast("list[object]", raw_events):
        if not isinstance(raw_event, dict):
            continue
        event = cast("dict[str, object]", raw_event)
        name = event.get("name")
        raw_attrs = event.get("attributes")
        if name == "Workflow run started":
            run_id = _event_attr_string(raw_attrs=raw_attrs, raw_key="run_id")
            if run_id is not None:
                return run_id
        if name == "Sandbox initialized" and fallback_id is None:
            fallback_id = _event_attr_string(raw_attrs=raw_attrs, raw_key="id")
    return fallback_id


def _event_attr_string(*, raw_attrs: object, raw_key: str) -> str | None:
    if not isinstance(raw_attrs, list):
        return None
    found: str | None = None
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if key != raw_key:
            continue
        found = _string_attr_value(entry=entry)
    return found


def _string_attr_value(*, entry: dict[str, object]) -> str | None:
    value = entry.get("value")
    if not isinstance(value, dict):
        return None
    string_value = cast("dict[str, object]", value).get("stringValue")
    return string_value if isinstance(string_value, str) else None


def enrich_span(
    *,
    span: dict[str, object],
    triple: dict[str, str],
) -> dict[str, object] | None:
    """Scrub + correlation-stamp one span; return None to REJECT it (§3.4).

    Rebuilds the span's `attributes` from the allowlist only (every other
    attribute is DROPPED — allowlist, not denylist), runs each forwarded
    string value through the fail-closed `scrub`, and stamps the backfilled
    correlation triple. If any allowlisted string value is credential-shaped
    (scrub returns the redaction marker), the WHOLE span is rejected
    (returns None) so a scrub miss fails closed rather than shipping a span
    that touched a credential. The rebuilt span preserves the non-attribute
    fields (`name`, `traceId`, `spanId`, `parentSpanId`, kind, timestamps).
    """
    forwarded_attrs: list[dict[str, object]] = []
    raw_attrs = span.get("attributes")
    if isinstance(raw_attrs, list):
        for raw in cast("list[object]", raw_attrs):
            if not isinstance(raw, dict):
                continue
            entry = cast("dict[str, object]", raw)
            key = entry.get("key")
            if not isinstance(key, str) or not is_allowed_attr(key=key):
                continue
            scalar = _scalar_value(entry=entry)
            if isinstance(scalar, str) and scrub(value=scalar) == REDACTION_MARKER:
                # A credential-shaped value in an allowlisted attribute:
                # reject the whole span (fail closed), do not partially ship.
                return None
            forwarded_attrs.append(attr(key=key, value=scalar))
    for triple_key, triple_value in triple.items():
        forwarded_attrs.append(attr(key=triple_key, value=triple_value))
    rebuilt: dict[str, object] = {k: v for k, v in span.items() if k != "attributes"}
    rebuilt["attributes"] = forwarded_attrs
    return rebuilt


def _scalar_value(*, entry: dict[str, object]) -> object:
    """Unwrap an OTLP attribute `value` block to its scalar Python value.

    Maps `stringValue` / `intValue` / `boolValue` back to a Python scalar;
    an int value arrives as a numeric string per OTLP/HTTP-JSON, so it is
    coerced back to `int`. An unrecognized shape falls back to the raw
    rendered text (which `scrub` then guards).
    """
    value = entry.get("value")
    if not isinstance(value, dict):
        return ""
    block = cast("dict[str, object]", value)
    if "boolValue" in block:
        return bool(block["boolValue"])
    if "intValue" in block:
        raw_int = block["intValue"]
        return int(raw_int) if isinstance(raw_int, str | int) else 0
    string_value = block.get("stringValue")
    if isinstance(string_value, str):
        return string_value
    return ""


@dataclass(kw_only=True)
class EnrichStage:
    """The host-local enrich/scrub stage (the §3.2 custom host processor).

    Holds the resumable file-tail cursor, the correlation join map, and the
    injected `SpanExporter`. `forward_once` runs ONE fail-open pass: tail
    new spans, learn correlation keys, backfill + scrub each, and batch the
    survivors per-dataset to the exporter. It NEVER raises — a forward
    error never blocks a dispatch (§3.2 fail-open) — but a credential-shaped
    span is dropped (fail-closed).
    """

    spans_path: Path
    exporter: SpanExporter
    join: CorrelationJoin = field(default_factory=CorrelationJoin)
    offset: int = 0

    def forward_once(self) -> ForwardResult:
        """Tail, enrich/scrub, and batch-forward new spans."""
        return self._forward_once()

    def _forward_once(self) -> ForwardResult:
        tail = tail_spans(spans_path=self.spans_path, offset=self.offset)
        # First pass: learn correlation keys from every ingested span so a
        # later span in the SAME batch can backfill from an earlier one.
        for ingested in tail.spans:
            self.join.observe(keys=correlation_keys_from_attrs(span=ingested.span))
        per_dataset: dict[str, list[dict[str, object]]] = {}
        forwarded = 0
        rejected = 0
        for ingested in tail.spans:
            keys = correlation_keys_from_attrs(span=ingested.span)
            triple = self.join.backfill(keys=keys)
            enriched = enrich_span(span=ingested.span, triple=triple)
            if enriched is None:
                rejected += 1
                continue
            dataset = honeycomb_dataset_for(resource_attrs=ingested.resource_attrs)
            per_dataset.setdefault(dataset, []).append(enriched)
            forwarded += 1
        exported = True
        for dataset, batch in per_dataset.items():
            if not self.exporter.export(spans=tuple(batch), dataset=dataset):
                exported = False
        self.offset = tail.offset
        return ForwardResult(
            ingested=len(tail.spans),
            forwarded=forwarded,
            rejected=rejected,
            exported=exported,
            offset=tail.offset,
        )
