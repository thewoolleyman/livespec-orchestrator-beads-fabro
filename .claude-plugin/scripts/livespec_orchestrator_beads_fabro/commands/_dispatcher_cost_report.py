"""Report-mode per-dispatch cost telemetry + stderr summary (LIVESPEC_COST_MODE=report).

The observability half of the GATE→REPORTER conversion. The user runs on a
SUBSCRIPTION (not API billing) and already sets spend limits at the
provider, so a fail-closed dollar gate is the wrong model; `report` mode
(the DEFAULT) instead CAPTURES and REPORTS what the wave WOULD cost at API
billing, and NEVER enforces it (`_dispatcher_cost.gate_wave` with
`cost_mode="report"` returns no refusals).

This module is the emit half of that report: for each green outcome whose
CC-token-derived cost the host OTLP receiver accrued into the per-dispatch
`CostSink` (`_dispatcher_cost_sink`), it

  * builds a leak-free per-work-item cost item — the derived micro-USD, a
    dollars view, the four per-category token sums, and the model basis
    (see below);
  * EMITS a `cost.report` OTLP span (per work-item, plus a wave-root span)
    through the SAME established local-span-file → enrich-stage egress path
    the reflection / verdict spans use (`_dispatcher_reflection._emit_spans`
    shape: one `ExportTraceServiceRequest` per line, every attribute built
    through the shared `_otel_scrub.attr`), so it is queryable in Honeycomb
    after the host-local enrich/scrub forward;
  * ECHOES a one-line human summary on STDERR (the established diagnostics
    channel — stdout stays the machine outcomes array).

Model-basis honesty (the load-bearing requirement). In the real session-6
runtime capture, CC's `claude_code.llm_request` spans carry NO `model`
attribute, so the cost-sink pricing falls back to the configured default
model (`claude-opus-4-8`). `CostReport.model_resolved` is True only when
EVERY contributing span carried a resolvable `model`; when it is False the
emitted span + the summary line are explicitly labeled a DEFAULT-MODEL
estimate (`livespec.cost.model_basis = "default:<model>"`,
`livespec.cost.model_resolved = false`, summary "(<model>-default
estimate)") so the reported number is never silently mis-attributed.

Credential hygiene: the span carries ONLY scalar numbers, the work-item /
dispatch ids, and a stable model-basis label — no goal text, no env values,
no remote URLs — and every attribute passes through the shared
`_otel_scrub.attr` (fail-closed credential-shape check) like every other
export. This module is stdlib-only (mirroring the reflection emitter).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_REPORT,
    usd_micros_to_usd,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostReport
from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr

__all__: list[str] = [
    "CostReportItem",
    "build_cost_report_item",
    "cost_report_summary_lines",
    "emit_cost_report",
]

# OTLP/HTTP JSON emission constants — the same shape the reflection emitter
# + the family capture script write (one ExportTraceServiceRequest per
# line), so the cost report rides the SAME local-span-file → enrich egress.
_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.cost-report"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


@dataclass(frozen=True, kw_only=True)
class CostReportItem:
    """The report-mode cost record for one green work-item (leak-free).

    `usd_micros` is the derived API-equivalent cost (None when no CC token
    telemetry arrived for the item — the unobservable condition, reported
    as such, never refused); `input_tokens` / `output_tokens` /
    `cache_creation_tokens` / `cache_read_tokens` are the per-category
    token sums; `model_basis` is the priced-model label (the resolved
    model id, or `default:<model>` when the model was NOT carried by the
    spans); `model_resolved` is False whenever any span fell back to the
    default model. `observable` is True iff a derived cost was present.
    """

    work_item_id: str
    usd_micros: int | None
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    model_basis: str
    model_resolved: bool
    observable: bool


def build_cost_report_item(
    *,
    work_item_id: str,
    report: CostReport | None,
    default_model: str | None = None,
) -> CostReportItem:
    """Build one work-item's cost report item from its sink `CostReport`.

    A None `report` (no CC telemetry accrued for the item) yields an
    UNOBSERVABLE item: zero token sums, `usd_micros=None`, `observable=False`
    — reported honestly as dark, never refused. An observable report carries
    the summed micro-USD + token sums, and the model basis is the resolved
    model id when `report.model_resolved` else `default:<model>` (the
    configured default, mirroring the cost sink's fallback) so a
    default-priced cost is never silently mis-attributed.
    """
    fallback_model = default_model if default_model is not None else DEFAULT_DISPATCH_COST_MODEL
    if report is None:
        return CostReportItem(
            work_item_id=work_item_id,
            usd_micros=None,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            model_basis=f"default:{fallback_model}",
            model_resolved=False,
            observable=False,
        )
    model_basis = fallback_model if report.model_resolved else f"default:{fallback_model}"
    return CostReportItem(
        work_item_id=work_item_id,
        usd_micros=report.usd_micros,
        input_tokens=report.input_tokens,
        output_tokens=report.output_tokens,
        cache_creation_tokens=report.cache_write_tokens,
        cache_read_tokens=report.cache_read_tokens,
        model_basis=model_basis,
        model_resolved=report.model_resolved,
        observable=True,
    )


def emit_cost_report(
    *,
    items: tuple[CostReportItem, ...],
    dispatch_id: str | None,
    spans_path: Path,
) -> None:
    """Emit the report-mode cost telemetry span(s) + the stderr summary.

    For each cost item it appends one `cost.report` OTLP span (carrying the
    derived USD, per-category token sums, model basis, and work-item id)
    under a `cost.report.wave` root span to `spans_path`, in the same
    one-ExportTraceServiceRequest-per-line shape the reflection emitter uses
    so the host-local enrich/scrub stage forwards it to Honeycomb; then it
    writes the one-line human summary to stderr (the diagnostics channel,
    NOT stdout). An empty `items` (no green run carried a cost) is a no-op.
    """
    if not items:
        return
    _emit_spans(items=items, dispatch_id=dispatch_id, spans_path=spans_path)
    _emit_summary(items=items)


def cost_report_summary_lines(*, items: tuple[CostReportItem, ...]) -> list[str]:
    """The one-line-per-item human cost summary (the stderr block content).

    Each line reads, e.g.:
    `cost (API-equiv estimate): $0.12  [in 1000 / out 500 / cache-create 0 /
    cache-read 0 tokens]  basis: claude-opus-4-8` — and when the model was
    NOT carried by the spans, the basis reads `default:claude-opus-4-8` and
    the line is tagged `(opus-default estimate)` so the number is honestly
    a default-model estimate. An unobservable item says so plainly.
    """
    return [_summary_line(item=item) for item in items]


def _summary_line(*, item: CostReportItem) -> str:
    """One item's stderr summary line (observable estimate or the dark note)."""
    head = f"cost (API-equiv estimate) [{item.work_item_id}]:"
    if not item.observable or item.usd_micros is None:
        return f"{head} unobservable (no CC token telemetry arrived); report-only, never enforced"
    dollars = usd_micros_to_usd(usd_micros=item.usd_micros)
    tokens = _token_summary(item=item)
    suffix = "" if item.model_resolved else f"  ({_default_tag(model_basis=item.model_basis)})"
    return f"{head} ${dollars:.2f}  [{tokens}]  basis: {item.model_basis}{suffix}"


def _token_summary(*, item: CostReportItem) -> str:
    """The four-category token breakdown rendered for the summary line."""
    counts = (
        f"in {item.input_tokens}",
        f"out {item.output_tokens}",
        f"cache-create {item.cache_creation_tokens}",
        f"cache-read {item.cache_read_tokens}",
    )
    return f"{' / '.join(counts)} tokens"


def _default_tag(*, model_basis: str) -> str:
    """Render the `(<model>-default estimate)` tag for an unresolved basis.

    `model_basis` is `default:<model>`; the tag uses the model's leading
    family token (e.g. `opus` from `default:claude-opus-4-8`) so the
    operator-facing note reads `(opus-default estimate)`.
    """
    model = model_basis.split(":", 1)[-1]
    family = model.removeprefix("claude-").split("-", 1)[0] or model
    return f"{family}-default estimate"


def _emit_summary(*, items: tuple[CostReportItem, ...]) -> None:
    _ = sys.stderr.write("\n".join(cost_report_summary_lines(items=items)) + "\n")


def _emit_spans(
    *,
    items: tuple[CostReportItem, ...],
    dispatch_id: str | None,
    spans_path: Path,
) -> None:
    """Append OTLP/HTTP JSON cost spans for the report to the spans file.

    One `cost.report.wave` root span (carrying the wave mode + the running
    per-session API-equivalent total) and one `cost.report` child per item,
    each with the leak-free derived USD + token + model-basis scalars built
    through the shared `_otel_scrub.attr`.
    """
    now_ns = time.time_ns()
    session_usd_micros = sum(item.usd_micros or 0 for item in items)
    wave_attrs: dict[str, object] = {
        "livespec.cost.mode": COST_MODE_REPORT,
        "livespec.cost.session_usd_micros": session_usd_micros,
        "livespec.cost.usd": f"{usd_micros_to_usd(usd_micros=session_usd_micros):.6f}",
    }
    if dispatch_id is not None and dispatch_id != "":
        wave_attrs["livespec.dispatch.id"] = dispatch_id
    wave_span = _build_span(
        name="cost.report.wave",
        span_id="cost-report-wave",
        attrs=wave_attrs,
        parent_id=None,
        start_ns=now_ns,
        end_ns=now_ns,
    )
    spans = [wave_span]
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
    line = _request_line(spans=spans)
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")


def _item_attrs(*, item: CostReportItem) -> dict[str, object]:
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
