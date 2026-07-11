"""Tests for the OTLP file-tail ingest extraction."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._otel_enrich_tail import tail_spans


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


def _request_line(*, service_name: str, spans: list[dict[str, object]]) -> str:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": "livespec-family"},
                        },
                    ]
                },
                "scopeSpans": [{"scope": {"name": "x", "version": "1"}, "spans": spans}],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _write_lines(*, path: Path, lines: list[str]) -> None:
    _ = path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def test_tail_missing_file_yields_empty_at_same_offset(tmp_path: Path) -> None:
    result = tail_spans(spans_path=tmp_path / "absent.jsonl", offset=42)
    assert result.spans == ()
    assert result.offset == 42


def test_tail_reads_new_lines_and_advances_cursor(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line_a = _request_line(service_name="livespec-dispatcher", spans=[_span(name="a", attrs=[])])
    _write_lines(path=path, lines=[line_a])
    first = tail_spans(spans_path=path, offset=0)
    assert len(first.spans) == 1
    assert first.spans[0].resource_attrs["service.name"] == "livespec-dispatcher"
    second = tail_spans(spans_path=path, offset=first.offset)
    assert second.spans == ()
    assert second.offset == first.offset


def test_tail_resets_when_file_truncated_under_cursor(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line = _request_line(service_name="svc", spans=[_span(name="a", attrs=[])])
    _write_lines(path=path, lines=[line])
    result = tail_spans(spans_path=path, offset=10_000)
    assert len(result.spans) == 1


def test_tail_skips_blank_and_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    good = _request_line(service_name="svc", spans=[_span(name="a", attrs=[])])
    _write_lines(
        path=path,
        lines=[
            "",
            "{not json",
            "[1, 2, 3]",
            json.dumps({"resourceSpans": "not-a-list"}),
            json.dumps({"resourceSpans": ["not-a-dict"]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": "nope"}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": ["bad"]}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": [{"spans": "bad"}]}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": [{"spans": ["bad"]}]}]}),
            good,
        ],
    )
    result = tail_spans(spans_path=path, offset=0)
    assert len(result.spans) == 1
    assert result.spans[0].span["name"] == "a"


def test_tail_resource_attrs_skip_malformed_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": "not-a-dict",
                    "scopeSpans": [{"spans": [_span(name="a", attrs=[])]}],
                }
            ]
        }
    )
    line_b = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {"attributes": "not-a-list"},
                    "scopeSpans": [{"spans": [_span(name="b", attrs=[])]}],
                }
            ]
        }
    )
    line_c = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            "bad",
                            {"key": 1, "value": {"stringValue": "x"}},
                            {"key": "service.name", "value": {"intValue": "9"}},
                            {"key": "service.namespace", "value": {"stringValue": "ns"}},
                        ]
                    },
                    "scopeSpans": [{"spans": [_span(name="c", attrs=[])]}],
                }
            ]
        }
    )
    _write_lines(path=path, lines=[line, line_b, line_c])
    result = tail_spans(spans_path=path, offset=0)
    assert {s.span["name"] for s in result.spans} == {"a", "b", "c"}
    c_attrs = next(s for s in result.spans if s.span["name"] == "c").resource_attrs
    assert c_attrs == {"service.namespace": "ns"}
