"""OTLP span rendering for Dispatcher calibration telemetry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    CalibrationRecord,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import tdd_span_fields
from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr

__all__: list[str] = [
    "calibration_request_line",
    "emit_calibration_span",
]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.calibration"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


def emit_calibration_span(*, record: CalibrationRecord, spans_path: Path, now_ns: int) -> None:
    """Append one OTLP/HTTP JSON span carrying calibration telemetry."""
    line = calibration_request_line(record=record, now_ns=now_ns)
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")


def calibration_request_line(*, record: CalibrationRecord, now_ns: int) -> str:
    """Build one OTLP `ExportTraceServiceRequest` JSON line."""
    span = {
        "traceId": _hex_id(key=f"calibration-trace:{record.work_item_id}", nbytes=16),
        "spanId": _hex_id(key=f"calibration-span:{record.work_item_id}", nbytes=8),
        "name": "dispatcher.calibration",
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(now_ns),
        "endTimeUnixNano": str(now_ns),
        "attributes": [_attr(key=key, value=value) for key, value in _attrs(record=record).items()],
    }
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
                        "spans": [span],
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _attrs(*, record: CalibrationRecord) -> dict[str, object]:
    """The span's attribute map.

    The TDD order fields are merged through `tdd_span_fields`, which carries
    only the OBSERVED ones: an unobservable signal must not egress, because
    the encoder below would ship it as the literal string `"None"` into a
    column the post-hoc derived column compares numerically.

    Plan slice S4's repaired fields (`bd-ib-tbgxm4`) ride here as well as on the
    journal, because this map and `calibration_journal_record` are two separate
    projections of one record: a field added to one and forgotten on the other
    fails nothing, and the half that is missing is the half an operator queries.
    Every key here must ALSO be named in `_otel_scrub.ATTRIBUTE_ALLOWLIST` — the
    receive stage rebuilds attributes from that allowlist, so an unnamed key is
    dropped with no error and the signal arrives silently empty.
    """
    return {
        "work.item.id": record.work_item_id,
        "converged": record.converged,
        "fix_loop_count": record.fix_loop_count,
        "outcome_class": record.outcome_class,
        "wall_clock_seconds": record.wall_clock_seconds,
        "token_cost_micros": record.token_cost_micros,
        "bounced_to_regroom": record.bounced_to_regroom,
        "acceptance_count": record.acceptance_count,
        "acceptance_count_source": record.acceptance_count_source,
        "merged_pr_diff_size": record.merged_pr_diff_size,
        "pr_open_diff_size": record.pr_open_diff_size,
        "dependency_fan_out": record.dependency_fan_out,
        "spec_surface_touched": record.spec_surface_touched,
        "dispatch_context_size": record.dispatch_context_size,
        "archetype": record.archetype,
        "repo": record.repo,
        "fabro.failure.cause": record.fabro_failure_cause,
        "fabro.failure.category": record.fabro_failure_category,
        "fabro.failure.signature": record.fabro_failure_signature,
        **(
            {"tdd.size_justified": record.tdd.size_justified}
            if record.tdd.size_justified is not None
            else {}
        ),
        **record.bounce_cap.as_record(),
        **tdd_span_fields(signals=record.tdd),
    }


def _hex_id(*, key: str, nbytes: int) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[: nbytes * 2]
