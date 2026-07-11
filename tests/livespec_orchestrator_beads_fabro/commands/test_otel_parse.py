"""Tests for the pure OTLP payload parsing helpers."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._otel_parse import (
    heartbeat_keys_from_metrics_request,
    ingested_spans_from_trace_request,
)


def _attr_entry(*, key: str, string_value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": string_value}}


def test_ingested_spans_from_trace_request_keeps_resource_attrs() -> None:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr_entry(key="service.name", string_value="cc-sandbox"),
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "agent.turn",
                                "attributes": [
                                    _attr_entry(key="work.item.id", string_value="bd-ib-grr")
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    spans = ingested_spans_from_trace_request(request=request)

    assert len(spans) == 1
    assert spans[0].resource_attrs == {"service.name": "cc-sandbox"}
    assert spans[0].span["name"] == "agent.turn"


def test_heartbeat_keys_from_metrics_request_prefers_data_point_id() -> None:
    request: dict[str, object] = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        _attr_entry(key="work.item.id", string_value="resource-fallback"),
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "attributes": [
                                                _attr_entry(
                                                    key="fabro.run_id",
                                                    string_value="run-winner",
                                                )
                                            ]
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert heartbeat_keys_from_metrics_request(request=request) == ("run-winner",)
