"""Coverage for the TDD order guard's OTLP decision span.

Every allow-or-refuse verdict the guard reaches is one span, so a refusal is
visible on the run's own trace rather than only in a session transcript. The
span carries five attributes — `tdd.decision`, `tdd.path`, `tdd.head_state`,
`tdd.reason` and `tdd.tool` — and each string value runs through the same
credential-shape scrub and length cap the host-side receive stage applies.

That last point is the reason this file reaches into the plugin package: the
hook cannot import the host-side `_otel_scrub` (it would couple a dev-time
hook in `.claude/hooks/` to the shipped plugin's internals, and the package is
not on the hook's import path), so it carries its own small copy of the three
scrub constants. Duplication that can drift silently is worth nothing, so the
tests below ASSERT the copies equal the originals, and assert that the
receive-side attribute allowlist admits all five keys — without which every
`tdd.*` attribute would be dropped on receipt and the signal would be silently
empty.

`.claude/hooks/` is not an importable package, so the module under test is
loaded by file location, inside each test body, with the file-exists assertion
first — so the Red commit fails on a genuine assertion rather than at
collection time.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    ATTR_MAX_LEN,
    ATTRIBUTE_ALLOWLIST,
    CREDENTIAL_URL_RE,
    REDACTION_MARKER,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_SPAN_PATH = _HOOKS_DIR / "livespec_tdd_order_span.py"
_POLICY_PATH = _HOOKS_DIR / "livespec_tdd_order_policy.py"

_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_SPAN_ID = "b7ad6b7169203331"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_NOW_NS = 1_760_000_000_000_000_000
_ENDPOINT = "http://172.17.0.1:4318"

_TDD_ATTRIBUTE_KEYS = (
    "tdd.decision",
    "tdd.path",
    "tdd.head_state",
    "tdd.reason",
    "tdd.tool",
)


def _load(*, path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"module not implemented yet: {path}"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_span() -> ModuleType:
    return _load(path=_SPAN_PATH, name="livespec_tdd_order_span_under_test")


def _load_policy() -> ModuleType:
    return _load(path=_POLICY_PATH, name="livespec_tdd_order_policy_for_span")


def _decision(*, reason: str = "closed-head", path: str = ".claude/hooks/g.py") -> Any:
    policy = _load_policy()
    return policy.Decision(
        decision=policy.REFUSE,
        reason=reason,
        head_state=policy.HEAD_CLOSED,
        path=path,
        tool="Write",
    )


def _body(*, span: ModuleType, decision: Any, parent_span_id: str = "") -> dict[str, Any]:
    return json.loads(
        span.decision_span_body(
            decision=decision,
            trace_id=_TRACE_ID,
            span_id=_SPAN_ID,
            parent_span_id=parent_span_id,
            now_ns=_NOW_NS,
        )
    )


def _only_span(*, body: dict[str, Any]) -> dict[str, Any]:
    resource_spans = body["resourceSpans"]
    assert len(resource_spans) == 1
    scope_spans = resource_spans[0]["scopeSpans"]
    assert len(scope_spans) == 1
    spans = scope_spans[0]["spans"]
    assert len(spans) == 1
    return spans[0]


def _attributes(*, body: dict[str, Any]) -> dict[str, Any]:
    return {entry["key"]: entry["value"] for entry in _only_span(body=body)["attributes"]}


# --- the five attributes ---------------------------------------------------


def test_the_span_carries_every_tdd_attribute() -> None:
    span = _load_span()
    attributes = _attributes(body=_body(span=span, decision=_decision()))
    assert set(_TDD_ATTRIBUTE_KEYS) <= set(attributes)
    assert attributes["tdd.decision"] == {"stringValue": "refuse"}
    assert attributes["tdd.path"] == {"stringValue": ".claude/hooks/g.py"}
    assert attributes["tdd.head_state"] == {"stringValue": "closed"}
    assert attributes["tdd.reason"] == {"stringValue": "closed-head"}
    assert attributes["tdd.tool"] == {"stringValue": "Write"}


def test_an_allow_decision_is_recorded_as_such() -> None:
    span = _load_span()
    policy = _load_policy()
    decision = policy.Decision(
        decision=policy.ALLOW,
        reason=policy.REASON_OPEN_RED,
        head_state=policy.HEAD_OPEN_RED,
        path=".claude/hooks/g.py",
        tool="Bash",
    )
    attributes = _attributes(body=_body(span=span, decision=decision))
    assert attributes["tdd.decision"] == {"stringValue": "allow"}
    assert attributes["tdd.head_state"] == {"stringValue": "open-red"}
    assert attributes["tdd.tool"] == {"stringValue": "Bash"}


def test_every_emitted_attribute_key_survives_the_receive_side_allowlist() -> None:
    span = _load_span()
    attributes = _attributes(body=_body(span=span, decision=_decision()))
    assert set(attributes) <= set(
        ATTRIBUTE_ALLOWLIST
    ), "an attribute absent from the host-side allowlist is DROPPED on receipt"


# --- the scrub -------------------------------------------------------------


def test_the_hook_scrub_constants_match_the_host_side_originals() -> None:
    span = _load_span()
    assert span.ATTR_MAX_LEN == ATTR_MAX_LEN
    assert span.REDACTION_MARKER == REDACTION_MARKER
    assert span.CREDENTIAL_URL_RE.pattern == CREDENTIAL_URL_RE.pattern


def test_a_credential_shaped_value_is_replaced_wholesale() -> None:
    span = _load_span()
    decision = _decision(reason="pushed to https://user:sekrit@example.com/repo")
    attributes = _attributes(body=_body(span=span, decision=decision))
    assert attributes["tdd.reason"] == {"stringValue": REDACTION_MARKER}


def test_a_long_value_is_truncated_rather_than_shipped_whole() -> None:
    span = _load_span()
    attributes = _attributes(body=_body(span=span, decision=_decision(reason="x" * 5_000)))
    value = attributes["tdd.reason"]["stringValue"]
    assert len(value) == ATTR_MAX_LEN


# --- the span envelope ----------------------------------------------------


def test_the_span_names_its_service_scope_and_timestamps() -> None:
    span = _load_span()
    body = _body(span=span, decision=_decision())
    resource = body["resourceSpans"][0]["resource"]
    resource_attributes = {entry["key"]: entry["value"] for entry in resource["attributes"]}
    assert resource_attributes["service.name"] == {"stringValue": span.SERVICE_NAME}
    assert resource_attributes["service.namespace"] == {"stringValue": span.SERVICE_NAMESPACE}

    scope = body["resourceSpans"][0]["scopeSpans"][0]["scope"]
    assert scope["name"] == span.SCOPE_NAME

    emitted = _only_span(body=body)
    assert emitted["name"] == span.SPAN_NAME
    assert emitted["traceId"] == _TRACE_ID
    assert emitted["spanId"] == _SPAN_ID
    assert emitted["startTimeUnixNano"] == str(_NOW_NS)
    assert emitted["endTimeUnixNano"] == str(_NOW_NS)


def test_a_parent_span_id_is_omitted_when_there_is_no_parent() -> None:
    span = _load_span()
    assert "parentSpanId" not in _only_span(body=_body(span=span, decision=_decision()))


def test_a_parent_span_id_is_carried_when_one_is_supplied() -> None:
    span = _load_span()
    body = _body(span=span, decision=_decision(), parent_span_id=_PARENT_SPAN_ID)
    assert _only_span(body=body)["parentSpanId"] == _PARENT_SPAN_ID


def test_the_body_is_deterministic_for_the_same_inputs() -> None:
    span = _load_span()
    decision = _decision()
    first = span.decision_span_body(
        decision=decision,
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )
    second = span.decision_span_body(
        decision=decision,
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )
    assert first == second


# --- emission -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_a_configured_endpoint_receives_the_span_as_an_otlp_traces_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _load_span()
    seen: dict[str, Any] = {}

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["data"] = request.data
        seen["headers"] = request.headers
        seen["method"] = request.get_method()
        seen["timeout"] = timeout
        return _FakeResponse(status=200)

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert span.emit_decision_span(
        decision=_decision(),
        endpoint=_ENDPOINT,
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )
    assert seen["url"] == f"{_ENDPOINT}/v1/traces"
    assert seen["method"] == "POST"
    assert seen["headers"]["Content-type"] == "application/json"
    attributes = _attributes(body=json.loads(seen["data"].decode("utf-8")))
    assert set(_TDD_ATTRIBUTE_KEYS) <= set(attributes)


def test_a_trailing_slash_on_the_endpoint_does_not_double_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _load_span()
    seen: dict[str, Any] = {}

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        seen["url"] = request.full_url
        return _FakeResponse(status=204)

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert span.emit_decision_span(
        decision=_decision(),
        endpoint=f"{_ENDPOINT}/",
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )
    assert seen["url"] == f"{_ENDPOINT}/v1/traces"


@pytest.mark.parametrize("status", [400, 500])
def test_a_rejecting_receiver_reports_a_failed_emission(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    span = _load_span()

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(status=status)

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert not span.emit_decision_span(
        decision=_decision(),
        endpoint=_ENDPOINT,
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )


def test_an_unreachable_receiver_reports_a_failed_emission_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _load_span()

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        raise OSError("connection refused")

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert not span.emit_decision_span(
        decision=_decision(),
        endpoint=_ENDPOINT,
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )


# --- endpoint resolution: absence is a successful no-op -------------------


def test_a_configured_endpoint_is_resolved_from_the_sandbox_env_var() -> None:
    span = _load_span()
    assert span.ENDPOINT_ENV_VAR == "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
    assert span.resolve_endpoint(environ={span.ENDPOINT_ENV_VAR: _ENDPOINT}) == _ENDPOINT


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_endpoint_resolves_to_no_endpoint(value: str) -> None:
    span = _load_span()
    assert span.resolve_endpoint(environ={span.ENDPOINT_ENV_VAR: value}) == ""


def test_an_absent_endpoint_resolves_to_no_endpoint() -> None:
    span = _load_span()
    assert span.resolve_endpoint(environ={}) == ""


def test_the_exporter_is_a_successful_no_op_when_no_endpoint_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No endpoint must mean no post, no error, and no raise.

    A human session with no receiver is the normal case for this guard, so the
    exporter has to stay silent there rather than erroring once per decision.
    """
    span = _load_span()
    posted: list[object] = []

    def _record(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        posted.append(request)
        return _FakeResponse(status=200)

    monkeypatch.setattr(span.urllib.request, "urlopen", _record)
    assert not span.emit_decision_span(
        decision=_decision(),
        endpoint="",
        trace_id=_TRACE_ID,
        span_id=_SPAN_ID,
        parent_span_id="",
        now_ns=_NOW_NS,
    )
    assert span.emit_for_decision(decision=_decision(), environ={}) == span.NO_ENDPOINT
    assert posted == []

    # Positive control for the assertion above: the SAME double does record a
    # post once an endpoint is configured, so the empty list is a measurement
    # rather than a double that was never wired in.
    configured = {span.ENDPOINT_ENV_VAR: _ENDPOINT}
    assert span.emit_for_decision(decision=_decision(), environ=configured) == span.EMITTED
    assert len(posted) == 1


# --- W3C trace context ----------------------------------------------------


def test_a_valid_traceparent_supplies_the_trace_and_parent_span_ids() -> None:
    span = _load_span()
    assert span.TRACE_CONTEXT_ENV_VAR == "TRACEPARENT"
    traceparent = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"
    assert span.trace_context(
        environ={span.TRACE_CONTEXT_ENV_VAR: traceparent}, fallback_trace_id="f" * 32
    ) == (_TRACE_ID, _PARENT_SPAN_ID)


def test_an_uppercase_traceparent_is_accepted_and_normalized() -> None:
    span = _load_span()
    traceparent = f"00-{_TRACE_ID.upper()}-{_PARENT_SPAN_ID.upper()}-01"
    assert span.trace_context(
        environ={span.TRACE_CONTEXT_ENV_VAR: traceparent}, fallback_trace_id="f" * 32
    ) == (_TRACE_ID, _PARENT_SPAN_ID)


@pytest.mark.parametrize(
    "traceparent",
    [
        "",
        "   ",
        "not-a-traceparent",
        f"01-{_TRACE_ID}-{_PARENT_SPAN_ID}-01",
        f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}",
        f"00-{_TRACE_ID[:-1]}-{_PARENT_SPAN_ID}-01",
        f"00-{_TRACE_ID}-{_PARENT_SPAN_ID[:-1]}-01",
        f"00-{'z' * 32}-{_PARENT_SPAN_ID}-01",
        f"00-{'0' * 32}-{_PARENT_SPAN_ID}-01",
        f"00-{_TRACE_ID}-{'0' * 16}-01",
    ],
)
def test_an_absent_or_malformed_traceparent_starts_a_root_trace(traceparent: str) -> None:
    span = _load_span()
    fallback = "a" * 32
    assert span.trace_context(
        environ={span.TRACE_CONTEXT_ENV_VAR: traceparent}, fallback_trace_id=fallback
    ) == (fallback, "")


def test_a_missing_traceparent_variable_starts_a_root_trace() -> None:
    span = _load_span()
    fallback = "b" * 32
    assert span.trace_context(environ={}, fallback_trace_id=fallback) == (fallback, "")


# --- the resolved emission preserves the run's trace context --------------


def test_the_emitted_span_joins_the_run_trace_named_by_traceparent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _load_span()
    seen: dict[str, Any] = {}

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        seen["data"] = request.data
        return _FakeResponse(status=200)

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    environ = {
        span.ENDPOINT_ENV_VAR: _ENDPOINT,
        span.TRACE_CONTEXT_ENV_VAR: f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01",
    }
    assert span.emit_for_decision(decision=_decision(), environ=environ) == span.EMITTED
    emitted = _only_span(body=json.loads(seen["data"].decode("utf-8")))
    assert emitted["traceId"] == _TRACE_ID
    assert emitted["parentSpanId"] == _PARENT_SPAN_ID
    assert emitted["spanId"] != _PARENT_SPAN_ID
    assert len(emitted["spanId"]) == 16
    assert int(emitted["startTimeUnixNano"]) > 0


def test_an_emission_with_no_traceparent_is_a_root_span(monkeypatch: pytest.MonkeyPatch) -> None:
    span = _load_span()
    seen: dict[str, Any] = {}

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        seen["data"] = request.data
        return _FakeResponse(status=200)

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert (
        span.emit_for_decision(decision=_decision(), environ={span.ENDPOINT_ENV_VAR: _ENDPOINT})
        == span.EMITTED
    )
    emitted = _only_span(body=json.loads(seen["data"].decode("utf-8")))
    assert "parentSpanId" not in emitted
    assert len(emitted["traceId"]) == 32


def test_an_undelivered_emission_is_reported_as_such(monkeypatch: pytest.MonkeyPatch) -> None:
    span = _load_span()

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        raise OSError("connection refused")

    monkeypatch.setattr(span.urllib.request, "urlopen", _urlopen)
    assert (
        span.emit_for_decision(decision=_decision(), environ={span.ENDPOINT_ENV_VAR: _ENDPOINT})
        == span.UNDELIVERED
    )


def test_the_three_emission_statuses_are_distinct_and_self_describing() -> None:
    span = _load_span()
    assert {span.EMITTED, span.NO_ENDPOINT, span.UNDELIVERED} == {
        "emitted",
        "no-endpoint",
        "undelivered",
    }
