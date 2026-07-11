"""Summary and OTLP span emission for dispatcher reflection."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "emit_spans",
    "emit_summary",
    "join_ids",
    "stage_summary",
]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.reflection"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


class FindingLike(Protocol):
    @property
    def category(self) -> str: ...

    @property
    def severity(self) -> str: ...

    @property
    def count(self) -> int: ...

    @property
    def subject(self) -> str: ...


class OutcomeLike(Protocol):
    @property
    def stage(self) -> str: ...


class ReportLike(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def item_count(self) -> int: ...

    @property
    def green_count(self) -> int: ...

    @property
    def failed_count(self) -> int: ...

    @property
    def blocked_count(self) -> int: ...

    @property
    def green_streak(self) -> int: ...

    @property
    def findings(self) -> tuple[FindingLike, ...]: ...


def stage_summary(*, outcomes: tuple[OutcomeLike, ...]) -> str:
    return ", ".join(sorted({o.stage for o in outcomes}))


def join_ids(*, ids: tuple[str, ...]) -> str:
    return ", ".join(ids)


def emit_summary(*, report: ReportLike) -> None:
    """Write the human reflection block to stderr (the loop summary channel)."""
    verdict = (
        f"{report.green_count} green / {report.failed_count} failed / "
        f"{report.blocked_count} blocked"
    )
    header = (
        f"reflection ({report.mode}): {report.item_count} item(s) - "
        f"{verdict}; trailing green streak {report.green_streak}"
    )
    lines = [header]
    if not report.findings:
        lines.append("reflection: no findings")
    for finding in report.findings:
        prefix = f"reflection [{finding.severity}] {finding.category} (x{finding.count})"
        lines.append(f"{prefix}: {finding.subject}")
    _ = write_stderr(text="\n".join(lines) + "\n")


def emit_spans(*, report: ReportLike, spans_path: Path) -> None:
    """Append OTLP/HTTP JSON spans for the reflection pass to the spans file."""
    now_ns = time.time_ns()
    pass_attrs: dict[str, object] = {
        "livespec.reflection.mode": report.mode,
        "livespec.reflection.item_count": report.item_count,
        "livespec.reflection.green_count": report.green_count,
        "livespec.reflection.failed_count": report.failed_count,
        "livespec.reflection.blocked_count": report.blocked_count,
        "livespec.reflection.green_streak": report.green_streak,
        "livespec.reflection.finding_count": len(report.findings),
    }
    pass_span = _build_span(
        name="reflection.pass",
        span_id="reflection-pass",
        attrs=pass_attrs,
        parent_id=None,
        start_ns=now_ns,
        end_ns=now_ns,
    )
    spans = [pass_span]
    for index, finding in enumerate(report.findings):
        finding_attrs: dict[str, object] = {
            "livespec.reflection.finding.category": finding.category,
            "livespec.reflection.finding.severity": finding.severity,
            "livespec.reflection.finding.count": finding.count,
            "livespec.reflection.finding.subject": finding.subject,
        }
        spans.append(
            _build_span(
                name="reflection.finding",
                span_id=f"reflection-finding-{index}",
                attrs=finding_attrs,
                parent_id="reflection-pass",
                start_ns=now_ns,
                end_ns=now_ns,
            )
        )
    line = _request_line(spans=spans)
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")


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
        "traceId": _hex_id(key="reflection-trace", nbytes=16),
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
