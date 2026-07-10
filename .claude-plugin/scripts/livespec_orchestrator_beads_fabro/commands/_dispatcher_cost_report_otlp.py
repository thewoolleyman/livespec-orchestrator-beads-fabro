"""OTLP JSON builders for `_dispatcher_cost_report`."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import usd_micros_to_usd
from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr

__all__: list[str] = ["cost_report_request_line"]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.cost-report"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


class CostReportItemLike(Protocol):
    """Cost-report item fields needed for OTLP serialization."""

    @property
    def work_item_id(self) -> str:
        """Work-item id."""
        ...

    @property
    def usd_micros(self) -> int | None:
        """Derived cost in micro-USD, when observable."""
        ...

    @property
    def input_tokens(self) -> int:
        """Input token count."""
        ...

    @property
    def output_tokens(self) -> int:
        """Output token count."""
        ...

    @property
    def cache_creation_tokens(self) -> int:
        """Cache creation token count."""
        ...

    @property
    def cache_read_tokens(self) -> int:
        """Cache read token count."""
        ...

    @property
    def model_basis(self) -> str:
        """Pricing model basis."""
        ...

    @property
    def model_resolved(self) -> bool:
        """Whether every contributing span carried a resolved model."""
        ...

    @property
    def observable(self) -> bool:
        """Whether derived cost was observable."""
        ...


def cost_report_request_line(
    *, items: tuple[CostReportItemLike, ...], dispatch_id: str | None, now_ns: int
) -> str:
    session_usd_micros = sum(item.usd_micros or 0 for item in items)
    wave_attrs: dict[str, object] = {
        "livespec.cost.mode": "report",
        "livespec.cost.session_usd_micros": session_usd_micros,
        "livespec.cost.usd": f"{usd_micros_to_usd(usd_micros=session_usd_micros):.6f}",
    }
    if dispatch_id is not None and dispatch_id != "":
        wave_attrs["livespec.dispatch.id"] = dispatch_id
    spans = [
        _build_span(
            name="cost.report.wave",
            span_id="cost-report-wave",
            attrs=wave_attrs,
            parent_id=None,
            start_ns=now_ns,
            end_ns=now_ns,
        )
    ]
    for index, item in enumerate(items):
        spans.append(
            _build_span(
                name="cost.report",
                span_id=f"cost-report-{index}",
                attrs=_item_attrs(item=item),
                parent_id="cost-report-wave",
                start_ns=now_ns,
                end_ns=now_ns,
            )
        )
    return _request_line(spans=spans)


def _item_attrs(*, item: CostReportItemLike) -> dict[str, object]:
    usd_micros = item.usd_micros or 0
    return {
        "work.item.id": item.work_item_id,
        "livespec.cost.usd_micros": usd_micros,
        "livespec.cost.usd": f"{usd_micros_to_usd(usd_micros=usd_micros):.6f}",
        "livespec.cost.input_tokens": item.input_tokens,
        "livespec.cost.output_tokens": item.output_tokens,
        "livespec.cost.cache_creation_tokens": item.cache_creation_tokens,
        "livespec.cost.cache_read_tokens": item.cache_read_tokens,
        "livespec.cost.model_basis": item.model_basis,
        "livespec.cost.model_resolved": item.model_resolved,
        "livespec.cost.observable": item.observable,
    }


def _build_span(
    *,
    name: str,
    span_id: str,
    attrs: dict[str, object],
    parent_id: str | None,
    start_ns: int,
    end_ns: int,
) -> dict[str, object]:
    span: dict[str, object] = {
        "traceId": _hex_id(key="cost-report-trace", nbytes=16),
        "spanId": _hex_id(key=span_id, nbytes=8),
        "name": name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [_attr(key=k, value=v) for k, v in attrs.items()],
    }
    if parent_id is not None:
        span["parentSpanId"] = _hex_id(key=parent_id, nbytes=8)
    return span


def _hex_id(*, key: str, nbytes: int) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[: nbytes * 2]


def _request_line(*, spans: list[dict[str, object]]) -> str:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": _OTLP_SERVICE_NAME}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": _OTLP_SERVICE_NAMESPACE},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _OTLP_SCOPE_NAME, "version": _OTLP_SCOPE_VERSION},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)
