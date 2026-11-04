"""The receiver allowlist carries the session wait and recovery vocabulary.

Scenario 159 of `SPECIFICATION/scenarios.md` and the "Bounded session waits and
observable inventory" clause require producers, the receiver allowlist and
consumers to agree on one vocabulary. The enrich stage REBUILDS a span's
attributes from `ATTRIBUTE_ALLOWLIST`, so a key the producer emits but the
allowlist does not name arrives in Honeycomb silently absent; emitter-only
proof therefore says nothing about delivery. These tests drive the shared
receiver seam itself, with a real localhost POST into `OtelReceiver`, and
assert both that every key survives with its OTLP TYPE intact (a measurement
that decays into a string is not queryable as a number) and that raw command,
prompt and environment material stays excluded.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._otel_enrich import enrich_span
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)

_STRING_KEYS = (
    "session.repository",
    "session.id",
    "session.wait.id",
    "session.wait.target.kind",
    "session.wait.target.id",
    "session.wait.return_reason",
    "session.observation.id",
    "session.observation.time",
    "session.observation.state",
    "session.obligation.id",
    "session.obligation.epoch",
    "session.obligation.deadline",
    "session.recovery.attempt_id",
    "session.recovery.state",
    "session.recovery.observed_at",
    "session.recovery.deferral_reason",
    "session.recovery.next_action",
    "session.recovery.coverage_state",
    "session.coverage.state",
    "overseer.alert.condition",
)
_INT_KEYS = (
    "session.observation.sequence",
    "session.wait.target_count",
    "session.wait.trigger_exit_code",
    "session.inventory.wait_count",
    "session.inventory.active_count",
    "session.inventory.unacknowledged_count",
    "session.export.dropped_count",
    "session.export.rejected_count",
    "session.export.failed_count",
    "session.recovery.duplicate_count",
    "session.recovery.fenced_count",
)
_DOUBLE_KEYS = (
    "session.wait.elapsed_seconds",
    "session.wait.remaining_seconds",
    "session.wait.budget_seconds",
    "session.wait.overdue_seconds",
    "session.observation.age_seconds",
    "session.obligation.overdue_seconds",
    "session.recovery.latency_seconds",
)
_BOOL_KEYS = (
    "session.wait.acknowledged",
    "session.wait.waiter_alive",
    "session.observation.fresh",
)
_ARRAY_KEYS = (
    "session.observation.unavailable",
    "session.recovery.unavailable",
)
_EXCLUDED_KEYS = (
    "session.wait.command",
    "session.prompt",
    "session.transcript",
    "session.environment",
)


def _entry(*, key: str, value: dict[str, object]) -> dict[str, object]:
    return {"key": key, "value": value}


def _vocabulary_attributes() -> list[dict[str, object]]:
    attributes: list[dict[str, object]] = []
    attributes.extend(_entry(key=key, value={"stringValue": f"{key}-v"}) for key in _STRING_KEYS)
    attributes.extend(_entry(key=key, value={"intValue": "7"}) for key in _INT_KEYS)
    attributes.extend(_entry(key=key, value={"doubleValue": 1.5}) for key in _DOUBLE_KEYS)
    attributes.extend(_entry(key=key, value={"boolValue": True}) for key in _BOOL_KEYS)
    attributes.extend(
        _entry(
            key=key,
            value={"arrayValue": {"values": [{"stringValue": "a"}, {"stringValue": "b"}]}},
        )
        for key in _ARRAY_KEYS
    )
    return attributes


def _span(*, attributes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "traceId": "0af7651916cd43dd8448eb211c80319c",
        "spanId": "b7ad6b7169203331",
        "name": "session.wait.armed",
        "attributes": attributes,
    }


def _forwarded(*, span: dict[str, object] | None) -> dict[str, dict[str, object]]:
    assert span is not None
    attributes = cast("list[dict[str, object]]", span["attributes"])
    return {
        cast("str", entry["key"]): cast("dict[str, object]", entry["value"]) for entry in attributes
    }


def test_every_session_key_survives_enrichment_with_its_otlp_type() -> None:
    forwarded = _forwarded(
        span=enrich_span(span=_span(attributes=_vocabulary_attributes()), triple={})
    )

    expected = {
        cast("str", entry["key"]): cast("dict[str, object]", entry["value"])
        for entry in _vocabulary_attributes()
    }
    assert forwarded == expected


def test_raw_command_prompt_and_environment_keys_stay_excluded() -> None:
    attributes = [_entry(key=key, value={"stringValue": "rm -rf /"}) for key in _EXCLUDED_KEYS] + [
        _entry(key="session.wait.id", value={"stringValue": "wait-1"})
    ]

    forwarded = _forwarded(span=enrich_span(span=_span(attributes=attributes), triple={}))

    assert set(forwarded) == {"session.wait.id"}


def test_credential_shaped_array_element_rejects_the_whole_span() -> None:
    leaking = _entry(
        key="session.observation.unavailable",
        value={"arrayValue": {"values": [{"stringValue": "https://user:secret@host/x"}]}},
    )

    assert enrich_span(span=_span(attributes=[leaking]), triple={}) is None


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True


def test_a_real_post_to_the_receiver_exports_the_typed_vocabulary(tmp_path: Path) -> None:
    exporter = _CapturingExporter()
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=HeartbeatSink(path=tmp_path / "beats.json"),
    )
    receiver.start()
    try:
        body = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            _entry(key="service.name", value={"stringValue": "livespec-dispatcher"})
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {
                                "name": "livespec.orchestrator.session_wait",
                                "version": "1.0.0",
                            },
                            "spans": [_span(attributes=_vocabulary_attributes())],
                        }
                    ],
                }
            ]
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{receiver.bound_port}/v1/traces",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5.0) as response:  # noqa: S310
            assert response.status == 200
    finally:
        receiver.stop()

    assert [dataset for _, dataset in exporter.calls] == ["livespec-dispatcher"]
    forwarded = _forwarded(span=exporter.calls[0][0][0])
    assert forwarded["session.wait.elapsed_seconds"] == {"doubleValue": 1.5}
    assert forwarded["session.observation.sequence"] == {"intValue": "7"}
    assert forwarded["session.observation.unavailable"] == {
        "arrayValue": {"values": [{"stringValue": "a"}, {"stringValue": "b"}]}
    }
