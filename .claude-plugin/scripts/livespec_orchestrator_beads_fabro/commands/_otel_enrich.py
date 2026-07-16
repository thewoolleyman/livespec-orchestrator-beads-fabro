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
   in-memory map keyed on `work.item.id` → `{livespec.dispatch.id,
   fabro.run_id}`, populated as dispatcher spans arrive. When a CC / fabro
   span carries ONE key of the triple, `CorrelationJoin` backfills the
   others as span attributes before forwarding, so the reflector joins on
   ONE key set (`GROUP BY work.item.id`) regardless of source.

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
from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr, is_allowed_attr, scrub

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
_TRIPLE_KEYS = (_WORK_ITEM_ID, _DISPATCH_ID, _FABRO_RUN_ID)


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
    """In-memory join map keyed on `work.item.id` (§3.3).

    Populated as dispatcher spans arrive (they carry the full triple);
    when a CC / fabro span later carries ONE key of the triple, the stage
    backfills the others. The map is process-scoped state (a mutable
    holder, not module globals) so the stage updates it without a `global`
    statement — matching the `_AutoTripState` pattern in
    `_dispatcher_reflection`.
    """

    _by_work_item: dict[str, dict[str, str]] = field(default_factory=dict)

    def observe(self, *, keys: dict[str, str]) -> None:
        """Record the triple values a span carries, keyed by `work.item.id`.

        Only learns from a span that carries `work.item.id` (the join key);
        a span lacking it cannot anchor the map. Each newly-seen triple key
        is merged in (later spans backfill earlier gaps without clobbering
        a known value).
        """
        work_item = keys.get(_WORK_ITEM_ID)
        if work_item is None:
            return
        known = self._by_work_item.setdefault(work_item, {})
        for triple_key in _TRIPLE_KEYS:
            value = keys.get(triple_key)
            if value is not None and triple_key not in known:
                known[triple_key] = value

    def backfill(self, *, keys: dict[str, str]) -> dict[str, str]:
        """Return the triple values to stamp on a span, backfilling from the map.

        Starts from the keys the span already carries (those win) and adds
        any missing triple member known for its `work.item.id`. A span with
        no `work.item.id` (and none learnable) gets only what it brought.
        """
        result = {k: v for k, v in keys.items() if k in _TRIPLE_KEYS}
        work_item = result.get(_WORK_ITEM_ID)
        if work_item is None:
            return result
        for triple_key, value in self._by_work_item.get(work_item, {}).items():
            _ = result.setdefault(triple_key, value)
        return result


def correlation_keys_from_attrs(*, span: dict[str, object]) -> dict[str, str]:
    """Extract the correlation-triple key/values a span already carries.

    Reads the span's OTLP `attributes` list and returns only the triple
    members present (string-valued). A span attribute is
    `{"key": ..., "value": {"stringValue": ...}}`; non-string or
    non-triple attributes are ignored here (correlation keys are strings).
    """
    found: dict[str, str] = {}
    raw_attrs = span.get("attributes")
    if not isinstance(raw_attrs, list):
        return found
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if not isinstance(key, str) or key not in _TRIPLE_KEYS:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            found[key] = string_value
    return found


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
            if isinstance(scalar, str) and scrub(value=scalar) != scalar:
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
