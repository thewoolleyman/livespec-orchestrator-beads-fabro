"""Tests for the sandbox Codex `[otel]` config projection (work-item bd-ib-dbzp).

The projection is what makes Codex spend telemetry EXIST. Measured 2026-09-08
against the pinned stack (`@agentclientprotocol/codex-acp@1.10.0` spawning
`codex app-server` from `@openai/codex@^0.153.3`): the adapter carries no OTel
wiring of its own and reads no `OTEL_*` variable, so the sandbox's Claude-Code
OTel overlay cannot reach it; the `codex app-server` it spawns DOES initialize
the provider, but `codex-rs/core/src/config/otel.rs::resolve_config` resolves
`trace_exporter` to `OtelExporterKind::None` whenever `[otel]` is absent from
`$CODEX_HOME/config.toml`. The sandbox provisioned `auth.json` and nothing else,
so Codex exported no span at all.

These assertions pin the exact document because a config that PARSES but names
the wrong exporter key is silently inert — the same failure shape that made the
earlier read-path fix unable to discharge this item.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_config_toml,
)

_EXPECTED = """[otel]
environment = "livespec"
metrics_exporter = "none"

[otel.trace_exporter.otlp-http]
endpoint = "http://172.17.0.1:4318/v1/traces"
protocol = "json"

[otel.span_attributes]
"work.item.id" = "bd-ib-dbzp"
"livespec.dispatch.id" = "dispatch-7"
"""


def test_renders_the_trace_exporter_span_attributes_and_statsig_opt_out() -> None:
    """The whole document, verbatim: exporter arm, correlation keys, no Statsig."""
    rendered = codex_otel_config_toml(
        endpoint="http://172.17.0.1:4318",
        work_item_id="bd-ib-dbzp",
        dispatch_id="dispatch-7",
    )
    assert rendered == _EXPECTED


def test_endpoint_is_signal_specific_and_tolerates_a_trailing_slash() -> None:
    """`with_endpoint` is used verbatim by codex, so the `/v1/traces` path is ours to add.

    `resolve_config`'s own comment records that OTLP HTTP endpoints are
    signal-specific in codex's config, so a bare authority would post spans to
    the receiver root rather than its `/v1/traces` route.
    """
    rendered = codex_otel_config_toml(
        endpoint="http://172.17.0.1:4318/",
        work_item_id="w-1",
        dispatch_id="d-1",
    )
    assert 'endpoint = "http://172.17.0.1:4318/v1/traces"' in rendered


def test_correlation_keys_are_the_two_the_cost_sink_gates_on() -> None:
    """`span_cost` returns None without one of these, so the pair is load-bearing.

    They ride `[otel.span_attributes]` rather than the resource, because
    codex's `SpanAttributesProcessor::on_start` calls `span.set_attribute`,
    and the cost sink reads the span's own `attributes` list.
    """
    rendered = codex_otel_config_toml(
        endpoint="http://host:4318",
        work_item_id="w-2",
        dispatch_id="d-2",
    )
    assert '"work.item.id" = "w-2"' in rendered
    assert '"livespec.dispatch.id" = "d-2"' in rendered


def test_log_exporter_is_left_unset_so_prompts_never_egress() -> None:
    """No `exporter` key: codex defaults the LOG exporter to None.

    Codex's log records carry prompt and tool-result content, and the host
    receiver exposes no `/v1/logs` route, so enabling them would be both a
    content-egress change and a 404.
    """
    rendered = codex_otel_config_toml(
        endpoint="http://host:4318",
        work_item_id="w-3",
        dispatch_id="d-3",
    )
    assert "\nexporter = " not in rendered
    assert "[otel.exporter" not in rendered
