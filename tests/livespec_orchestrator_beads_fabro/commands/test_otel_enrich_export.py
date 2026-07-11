"""Tests for Honeycomb egress helpers used by the OTLP enrich stage."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_enrich_export import (
    HoneycombHttpExporter,
    honeycomb_dataset_for,
)

_URLOPEN = "urllib.request.urlopen"
_EXPORT_SLEEP = "livespec_orchestrator_beads_fabro.commands._otel_enrich_export.time.sleep"


def _no_sleep(_seconds: float) -> None:
    """Drop-in for `time.sleep` so retry tests never actually block."""
    return None


def _attr_entry(*, key: str, string_value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": string_value}}


def _span(*, name: str, attrs: list[dict[str, object]]) -> dict[str, object]:
    return {
        "traceId": "0f47cb389c78d595429094ccc72a4dca",
        "spanId": "0f47cb389c78d595",
        "name": name,
        "kind": 1,
        "startTimeUnixNano": "1",
        "endTimeUnixNano": "2",
        "attributes": attrs,
    }


@dataclass(kw_only=True)
class _FakeResponse:
    status: int

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_dataset_derives_from_service_name_with_sentinel_fallback() -> None:
    assert honeycomb_dataset_for(resource_attrs={"service.name": "livespec-dispatcher"}) == (
        "livespec-dispatcher"
    )
    assert honeycomb_dataset_for(resource_attrs={}) == "livespec-unknown"


def test_http_exporter_posts_with_team_and_dataset_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_urlopen(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["data"] = request.data
        captured["timeout"] = timeout
        return _FakeResponse(status=200)

    monkeypatch.setattr(_URLOPEN, _fake_urlopen)
    exporter = HoneycombHttpExporter(ingest_key="ingest-key-xyz")
    span = _span(name="a", attrs=[_attr_entry(key="repo", string_value="livespec")])
    assert exporter.export(spans=(span,), dataset="livespec-dispatcher") is True
    headers = cast("dict[str, str]", captured["headers"])
    assert headers["X-honeycomb-team"] == "ingest-key-xyz"
    assert headers["X-honeycomb-dataset"] == "livespec-dispatcher"
    assert captured["url"] == "https://api.honeycomb.io/v1/traces"
    body = json.loads(cast("bytes", captured["data"]).decode("utf-8"))
    assert body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "a"


def test_http_exporter_empty_batch_is_a_noop_success() -> None:
    exporter = HoneycombHttpExporter(ingest_key="k")
    assert exporter.export(spans=(), dataset="svc") is True


def test_http_exporter_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def _flaky_urlopen(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.URLError("transient")
        return _FakeResponse(status=202)

    monkeypatch.setattr(_URLOPEN, _flaky_urlopen)
    monkeypatch.setattr(_EXPORT_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k")
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is True
    assert len(attempts) == 2


def test_http_exporter_returns_false_after_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def _always_fail(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        attempts.append(1)
        raise urllib.error.URLError("down")

    monkeypatch.setattr(_URLOPEN, _always_fail)
    monkeypatch.setattr(_EXPORT_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k", max_retries=2)
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is False
    assert len(attempts) == 2


def test_http_exporter_treats_5xx_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _serverdown(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        return _FakeResponse(status=503)

    monkeypatch.setattr(_URLOPEN, _serverdown)
    monkeypatch.setattr(_EXPORT_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k", max_retries=1)
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is False
