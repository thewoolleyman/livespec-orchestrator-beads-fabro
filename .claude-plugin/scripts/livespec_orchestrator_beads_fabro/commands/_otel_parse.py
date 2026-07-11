"""Pure OTLP payload parsing helpers for the live receiver."""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands._otel_enrich import IngestedSpan

__all__: list[str] = [
    "heartbeat_keys_from_metrics_request",
    "ingested_spans_from_trace_request",
]

_HEARTBEAT_KEY_PREFERENCE = (
    "fabro.run_id",
    "livespec.dispatch.id",
    "work.item.id",
    "session.id",
)


def ingested_spans_from_trace_request(*, request: dict[str, object]) -> tuple[IngestedSpan, ...]:
    """Parse an OTLP/HTTP-JSON ExportTraceServiceRequest into IngestedSpans."""
    resource_spans = request.get("resourceSpans")
    if not isinstance(resource_spans, list):
        return ()
    ingested: list[IngestedSpan] = []
    for raw_rs in cast("list[object]", resource_spans):
        if not isinstance(raw_rs, dict):
            continue
        rs = cast("dict[str, object]", raw_rs)
        resource_attrs = _flatten_resource_attrs(resource=rs.get("resource"))
        scope_spans = rs.get("scopeSpans")
        if not isinstance(scope_spans, list):
            continue
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


def heartbeat_keys_from_metrics_request(*, request: dict[str, object]) -> tuple[str, ...]:
    """Extract the per-data-point heartbeat keys from an OTLP metrics request."""
    resource_metrics = request.get("resourceMetrics")
    if not isinstance(resource_metrics, list):
        return ()
    keys: list[str] = []
    for raw_rm in cast("list[object]", resource_metrics):
        if not isinstance(raw_rm, dict):
            continue
        rm = cast("dict[str, object]", raw_rm)
        resource_ids = _correlation_ids_from_attrs(
            raw_attrs=_resource_attr_list(resource=rm.get("resource"))
        )
        keys.extend(
            _keys_from_scope_metrics(
                scope_metrics=rm.get("scopeMetrics"),
                resource_ids=resource_ids,
            )
        )
    return tuple(keys)


def _keys_from_scope_metrics(*, scope_metrics: object, resource_ids: dict[str, str]) -> list[str]:
    if not isinstance(scope_metrics, list):
        return []
    keys: list[str] = []
    for raw_sm in cast("list[object]", scope_metrics):
        if not isinstance(raw_sm, dict):
            continue
        metrics = cast("dict[str, object]", raw_sm).get("metrics")
        if not isinstance(metrics, list):
            continue
        for raw_metric in cast("list[object]", metrics):
            if isinstance(raw_metric, dict):
                keys.extend(
                    _keys_from_metric(
                        metric=cast("dict[str, object]", raw_metric),
                        resource_ids=resource_ids,
                    )
                )
    return keys


def _keys_from_metric(*, metric: dict[str, object], resource_ids: dict[str, str]) -> list[str]:
    keys: list[str] = []
    for data_point in _data_points_of(metric=metric):
        ids = dict(resource_ids)
        ids.update(_correlation_ids_from_attrs(raw_attrs=data_point.get("attributes")))
        chosen = _preferred_key(ids=ids)
        if chosen is not None:
            keys.append(chosen)
    return keys


def _data_points_of(*, metric: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Return the dataPoints across whichever metric shape is present."""
    points: list[dict[str, object]] = []
    for shape in ("gauge", "sum", "histogram", "summary", "exponentialHistogram"):
        block = metric.get(shape)
        if not isinstance(block, dict):
            continue
        data_points = cast("dict[str, object]", block).get("dataPoints")
        if not isinstance(data_points, list):
            continue
        for raw_point in cast("list[object]", data_points):
            if isinstance(raw_point, dict):
                points.append(cast("dict[str, object]", raw_point))
    return tuple(points)


def _preferred_key(*, ids: dict[str, str]) -> str | None:
    for candidate in _HEARTBEAT_KEY_PREFERENCE:
        value = ids.get(candidate)
        if value is not None and value != "":
            return value
    return None


def _resource_attr_list(*, resource: object) -> object:
    if not isinstance(resource, dict):
        return None
    return cast("dict[str, object]", resource).get("attributes")


def _correlation_ids_from_attrs(*, raw_attrs: object) -> dict[str, str]:
    """Extract string-valued correlation/session ids from an OTLP attrs list."""
    found: dict[str, str] = {}
    if not isinstance(raw_attrs, list):
        return found
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if not isinstance(key, str) or key not in _HEARTBEAT_KEY_PREFERENCE:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            found[key] = string_value
    return found


def _flatten_resource_attrs(*, resource: object) -> dict[str, str]:
    """Flatten an OTLP `resource.attributes` block to a `key -> str` map."""
    out: dict[str, str] = {}
    raw_attrs = _resource_attr_list(resource=resource)
    if not isinstance(raw_attrs, list):
        return out
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
            out[key] = string_value
    return out
