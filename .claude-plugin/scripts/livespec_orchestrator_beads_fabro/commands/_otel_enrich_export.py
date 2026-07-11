"""Honeycomb egress helpers for the host-local OTLP enrich stage."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

__all__: list[str] = [
    "HoneycombHttpExporter",
    "SpanExporter",
    "honeycomb_dataset_for",
]

# Honeycomb OTLP/HTTP ingest endpoint + auth header name. The dataset is
# derived per-request from `service.name`.
_HONEYCOMB_TRACES_URL = "https://api.honeycomb.io/v1/traces"
_HONEYCOMB_TEAM_HEADER = "x-honeycomb-team"
_HONEYCOMB_DATASET_HEADER = "x-honeycomb-dataset"
_DEFAULT_DATASET = "livespec-unknown"

# Egress batching + retry. Bounded so a Honeycomb outage degrades the
# pipeline (fail-open) rather than wedging the host.
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
_DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0

# HTTP 2xx is a successful Honeycomb ingest; anything else is a failed
# export (retried, then fail-open).
_HTTP_OK_MIN = 200
_HTTP_OK_MAX_EXCLUSIVE = 300


class SpanExporter(Protocol):
    """Egress seam: ship a batch of scrubbed spans for one dataset.

    Returns True on a successful export, False on a (bounded-retry-
    exhausted) failure. NEVER raises — the enrich stage is fail-open
    toward the pipeline, so a Honeycomb outage is a False return, not an
    exception that could escape toward a dispatch.
    """

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        """Export a batch of OTLP/HTTP-JSON spans to the given dataset."""
        ...


def honeycomb_dataset_for(*, resource_attrs: dict[str, str]) -> str:
    """Derive the Honeycomb dataset name from a span line's resource attrs.

    Honeycomb routes a trace dataset by `service.name`; a span line missing it
    falls back to a stable sentinel so the span still egresses to a knowable
    dataset.
    """
    return resource_attrs.get("service.name", _DEFAULT_DATASET)


@dataclass(frozen=True, kw_only=True)
class HoneycombHttpExporter:
    """Stdlib-only OTLP/HTTP-JSON exporter to Honeycomb with bounded retry.

    Uses `urllib.request` to POST a one-`ExportTraceServiceRequest` batch to
    Honeycomb with the ingest-only key in the `x-honeycomb-team` header and
    the dataset in `x-honeycomb-dataset`. Retries up to `max_retries` on a
    transport / 5xx error with linear backoff; returns False once retries are
    exhausted, never raising toward the enrich stage.
    """

    ingest_key: str
    url: str = _HONEYCOMB_TRACES_URL
    max_retries: int = _DEFAULT_MAX_RETRIES
    backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS
    timeout_seconds: float = _DEFAULT_HTTP_TIMEOUT_SECONDS

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        if not spans:
            return True
        body = _export_request_bytes(spans=spans, dataset=dataset)
        for attempt in range(self.max_retries):
            if self._post(body=body, dataset=dataset):
                return True
            if attempt + 1 < self.max_retries:
                time.sleep(self.backoff_seconds * (attempt + 1))
        return False

    def _post(self, *, body: bytes, dataset: str) -> bool:
        request = urllib.request.Request(  # noqa: S310 — fixed https Honeycomb URL.
            self.url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                _HONEYCOMB_TEAM_HEADER: self.ingest_key,
                _HONEYCOMB_DATASET_HEADER: dataset,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                status = response.status
        except (urllib.error.URLError, OSError):
            return False
        return _HTTP_OK_MIN <= status < _HTTP_OK_MAX_EXCLUSIVE


def _export_request_bytes(*, spans: tuple[dict[str, object], ...], dataset: str) -> bytes:
    """Serialize a span batch as one OTLP/HTTP-JSON ExportTraceServiceRequest."""
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": dataset}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": "livespec-family"},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "livespec.otel.enrich", "version": "0.1.0"},
                        "spans": list(spans),
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True).encode("utf-8")
