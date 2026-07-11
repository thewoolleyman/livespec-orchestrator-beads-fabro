"""OTLP span and human-summary emission for the out-of-band reflector."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import ReflectorFinding
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = ["build_span", "emit_spans", "emit_summary", "hex_id", "request_line"]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.reflector"
_OTLP_SCOPE_VERSION = "0.1.0"
_EVAL_SPAN_NAME = "gen_ai.evaluation.result"
_SPAN_KIND_INTERNAL = 1


class _SummaryReport(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def findings(self) -> tuple[ReflectorFinding, ...]: ...

    @property
    def filed(self) -> tuple[str, ...]: ...

    @property
    def bumped(self) -> tuple[str, ...]: ...

    @property
    def muted(self) -> tuple[str, ...]: ...

    @property
    def digested(self) -> tuple[str, ...]: ...

    @property
    def lesson_proposed(self) -> bool: ...


def emit_spans(*, findings: tuple[ReflectorFinding, ...], spans_path: Path) -> None:
    """Append one `gen_ai.evaluation.result` span per finding to the spans file."""
    if not findings:
        return
    now_ns = time.time_ns()
    spans: list[dict[str, object]] = []
    for index, finding in enumerate(findings):
        eval_attrs: dict[str, object] = {
            "gen_ai.evaluation.name": finding.category,
            "gen_ai.evaluation.score": str(finding.score),
            "gen_ai.evaluation.label": finding.label,
            "gen_ai.evaluation.severity": finding.severity,
            "livespec.reflection.finding.category": finding.category,
            "livespec.reflection.finding.severity": finding.severity,
            "livespec.reflection.finding.count": finding.occurrences,
        }
        if finding.work_item_id is not None:
            eval_attrs["work.item.id"] = finding.work_item_id
        spans.append(
            build_span(
                name=_EVAL_SPAN_NAME,
                span_id=f"reflector-eval-{index}",
                attrs=eval_attrs,
                parent_id=dispatch_parent_id(work_item_id=finding.work_item_id),
                start_ns=now_ns,
                end_ns=now_ns,
            )
        )
    line = request_line(spans=spans)
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")


def emit_summary(*, report: _SummaryReport) -> None:
    """Echo the reflector findings into the human summary on STDERR."""
    header = (
        f"reflector-oob ({report.mode}): {len(report.findings)} finding(s) - "
        f"{len(report.filed)} filed, {len(report.bumped)} bumped, "
        f"{len(report.muted)} muted, {len(report.digested)} digest-only"
    )
    lines = [header]
    for finding in report.findings:
        lines.append(f"reflector-oob [{finding.severity}] {finding.category}: {finding.subject}")
    if report.lesson_proposed:
        lines.append("reflector-oob: proposed a lesson via PR (merge to ratify)")
    _ = write_stderr(text="\n".join(lines) + "\n")


def build_span(
    *,
    name: str,
    span_id: str,
    attrs: dict[str, object],
    parent_id: str | None,
    start_ns: int,
    end_ns: int,
) -> dict[str, object]:
    span: dict[str, object] = {
        "traceId": hex_id(key="reflector-trace", nbytes=16),
        "spanId": hex_id(key=span_id, nbytes=8),
        "name": name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [attr(key=k, value=v) for k, v in attrs.items()],
    }
    if parent_id is not None:
        span["parentSpanId"] = hex_id(key=parent_id, nbytes=8)
    return span


def hex_id(*, key: str, nbytes: int) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[: nbytes * 2]


def request_line(*, spans: list[dict[str, object]]) -> str:
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


def dispatch_parent_id(*, work_item_id: str | None) -> str | None:
    if work_item_id is None:
        return None
    return f"dispatch-{work_item_id}"
