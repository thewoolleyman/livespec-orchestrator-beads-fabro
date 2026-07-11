"""OTLP file-tail ingest helpers for the host-local enrich stage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "IngestedSpan",
    "TailResult",
    "tail_spans",
]


@dataclass(frozen=True, kw_only=True)
class IngestedSpan:
    """One span read off a local span file, with its line's resource attrs.

    `resource_attrs` is the per-line `service.name` / `service.namespace`
    resource block (flattened to a `key -> str` map) so the exporter can
    derive the Honeycomb dataset and the enrich stage can keep
    resource-scoped context. `span` is the raw OTLP/HTTP-JSON span object
    (it carries `name`, `traceId`, `spanId`, `attributes`, ...).
    """

    resource_attrs: dict[str, str]
    span: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class TailResult:
    """The result of one file-tail pass: new spans + the advanced cursor.

    `offset` is the byte position to resume from on the next pass (a
    resumable cursor so a long-lived stage never re-reads forwarded lines).
    """

    spans: tuple[IngestedSpan, ...]
    offset: int


def tail_spans(*, spans_path: Path, offset: int) -> TailResult:
    """Read the span file's new lines past `offset`; return spans + new cursor.

    Each line is one OTLP/HTTP-JSON `ExportTraceServiceRequest`. The reader
    is fail-open: a missing file yields an empty result at the same offset;
    a malformed / structurally-unexpected line is skipped (the cursor still
    advances past it so the stage never wedges on one bad line).
    """
    if not spans_path.is_file():
        return TailResult(spans=(), offset=offset)
    raw = spans_path.read_bytes()
    if offset > len(raw):
        offset = 0
    new_text = raw[offset:].decode("utf-8", errors="replace")
    ingested: list[IngestedSpan] = []
    for line in new_text.splitlines():
        ingested.extend(_parse_line(line=line))
    return TailResult(spans=tuple(ingested), offset=len(raw))


def _parse_line(*, line: str) -> tuple[IngestedSpan, ...]:
    """Parse one `ExportTraceServiceRequest` line into its spans (fail-open)."""
    stripped = line.strip()
    if not stripped:
        return ()
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, dict):
        return ()
    resource_spans = cast("dict[str, object]", parsed).get("resourceSpans")
    if not isinstance(resource_spans, list):
        return ()
    ingested: list[IngestedSpan] = []
    for raw_rs in cast("list[object]", resource_spans):
        if isinstance(raw_rs, dict):
            ingested.extend(_parse_resource_spans(resource_spans=cast("dict[str, object]", raw_rs)))
    return tuple(ingested)


def _parse_resource_spans(*, resource_spans: dict[str, object]) -> tuple[IngestedSpan, ...]:
    resource_attrs = _resource_attrs(resource_spans=resource_spans)
    scope_spans = resource_spans.get("scopeSpans")
    if not isinstance(scope_spans, list):
        return ()
    ingested: list[IngestedSpan] = []
    for raw_scope in cast("list[object]", scope_spans):
        if not isinstance(raw_scope, dict):
            continue
        spans = cast("dict[str, object]", raw_scope).get("spans")
        if not isinstance(spans, list):
            continue
        for raw_span in cast("list[object]", spans):
            if isinstance(raw_span, dict):
                ingested.append(
                    IngestedSpan(
                        resource_attrs=resource_attrs,
                        span=cast("dict[str, object]", raw_span),
                    )
                )
    return tuple(ingested)


def _resource_attrs(*, resource_spans: dict[str, object]) -> dict[str, str]:
    resource = resource_spans.get("resource")
    if not isinstance(resource, dict):
        return {}
    raw_attrs = cast("dict[str, object]", resource).get("attributes")
    if not isinstance(raw_attrs, list):
        return {}
    out: dict[str, str] = {}
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        value = _string_value(entry=entry)
        if isinstance(key, str) and value is not None:
            out[key] = value
    return out


def _string_value(*, entry: dict[str, object]) -> str | None:
    value = entry.get("value")
    if not isinstance(value, dict):
        return None
    string_value = cast("dict[str, object]", value).get("stringValue")
    return string_value if isinstance(string_value, str) else None
