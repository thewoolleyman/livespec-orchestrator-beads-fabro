"""The sandbox Codex `[otel]` config projection (work-item bd-ib-dbzp).

WHY THIS MODULE EXISTS. Codex spend telemetry was discharged in the emitter
and measurably absent at the destination: over seven days the cost
model-basis attribute took exactly two values, both Anthropic, while the
same query returned non-zero token sums for the Anthropic basis. No Codex
span ever arrived, so the read path in `_dispatcher_cost_sink_span` had no
population to act on and no change there could have fixed it.

THE CAUSE, measured 2026-09-08 against the pinned stack rather than cited
from the 2026-07-12 survey, which studied a DIFFERENT package
(`@zed-industries/codex-acp@0.16.0`, a Rust binary vendoring codex-core):

- The pinned adapter is `@agentclientprotocol/codex-acp@1.10.0`, a
  JavaScript bundle. It contains zero `otel` references and reads no
  `OTEL_*` variable, so the sandbox's Claude-Code OTel overlay — which
  Claude Code honors — cannot reach Codex at all.
- That adapter spawns `codex app-server` (from `@openai/codex@^0.153.3`)
  with an inherited environment. Unlike the `mcp-server` entry point the
  older survey generalized from, `app-server` DOES initialize the
  provider: `codex-rs/app-server/src/lib.rs` calls
  `codex_core::otel_init::build_provider` under service name
  `codex-app-server`.
- codex-core resolves that provider's exporters from the `[otel]` table of
  `$CODEX_HOME/config.toml` ONLY. `codex-rs/core/src/config/otel.rs`
  `resolve_config` reads
  `trace_exporter = config.trace_exporter.unwrap_or(OtelExporterKind::None)`,
  so an absent table means the trace exporter is None.
- The sandbox provisioned `$CODEX_HOME/auth.json` and NOTHING ELSE — no
  `config.toml`, therefore no `[otel]` table.

So Codex exported no span whatsoever. The token attributes it would carry
(`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`, recorded on the
responses span in `codex-rs/otel/src/events/session_telemetry.rs`) are
already read by `_dispatcher_cost_sink_span` and already carried by the
`_otel_scrub` allowlist. Nothing downstream was missing; the emission was.

WHAT THIS PROJECTION SETS, and why each key is load-bearing:

- `trace_exporter` as `otlp-http`, pointed at the host receiver's
  signal-specific `/v1/traces` route. codex passes the configured endpoint
  to `with_endpoint` VERBATIM, and `resolve_config`'s own comment records
  that its OTLP HTTP endpoints are signal-specific, so the path is ours to
  supply. `protocol = "json"` because the host receiver is JSON-only.
- `span_attributes` carrying the correlation pair. `span_cost` returns None
  for a span bearing no `work.item.id` / `livespec.dispatch.id`, so without
  these the tokens would arrive and still accrue nothing. They belong on the
  SPAN rather than the resource because codex's `SpanAttributesProcessor`
  calls `span.set_attribute` per span, and the cost sink reads the span's
  own `attributes` list.
- `metrics_exporter = "none"`. This one REDUCES egress that exists today:
  codex defaults its metrics exporter to `Statsig`, which in release builds
  resolves to `https://ab.chatgpt.com/otlp/v1/metrics` with a built-in
  OpenAI key. Every factory Codex node has been shipping metrics there.
  Writing an `[otel]` table without this key would leave that default in
  force, so declining to set it is also a decision — this takes the
  minimal-egress side.
- NO `exporter` key, so the LOG exporter stays None. Codex log records carry
  prompt and tool-result content, and the host receiver exposes no `/v1/logs`
  route, so enabling them would be both a content-egress change and a 404.

The enum is externally tagged and kebab-cased (`OtelExporterKind` in
`codex-rs/config/src/types.rs`), which is why the exporter arm renders as a
nested `[otel.trace_exporter.otlp-http]` table and the off switch renders as
the bare string `"none"`. A config that parses but names the wrong arm is
SILENTLY INERT, which is the failure shape that kept this item open, so the
paired test pins the whole document rather than probing for a key.
"""

from __future__ import annotations

import json

__all__: list[str] = [
    "CODEX_OTEL_CONFIG_ENV_VAR",
    "codex_otel_config_toml",
    "codex_otel_env_lines",
    "codex_otel_prepare_steps_block",
]

# The env-var NAME (not a secret) the rendered config rides into the sandbox
# on, mirroring how CODEX_AUTH_JSON carries the credential snapshot: the
# container-level env table holds the value and the prepare step writes it to
# a file, so the overlay needs no inline heredoc.
CODEX_OTEL_CONFIG_ENV_VAR = "CODEX_OTEL_CONFIG_TOML"

# The receiver route spans are POSTed to. codex uses the configured endpoint
# verbatim, so the signal path must be part of it.
_TRACES_PATH = "/v1/traces"

# `environment` tags every exported span, which is what lets a destination
# query separate factory-originated Codex spans from any other codex traffic.
_OTEL_ENVIRONMENT = "livespec"

# The host receiver decodes OTLP/HTTP JSON only.
_HTTP_PROTOCOL = "json"

# The `OtelExporterKind::None` unit variant, kebab-cased by serde.
_EXPORTER_OFF = "none"

# The two correlation keys `span_cost` gates on, most-specific first.
_WORK_ITEM_ATTR = "work.item.id"
_DISPATCH_ATTR = "livespec.dispatch.id"


def codex_otel_config_toml(*, endpoint: str, work_item_id: str, dispatch_id: str) -> str:
    """Render the `$CODEX_HOME/config.toml` body enabling Codex trace export.

    `endpoint` is the sandbox→host receiver base (no signal path); the
    `/v1/traces` route is appended here. Values are `json.dumps`-ed to
    TOML-quote them, the same encoding the overlay uses for every other
    projected literal.
    """
    traces_endpoint = endpoint.rstrip("/") + _TRACES_PATH
    return (
        "[otel]\n"
        f"environment = {json.dumps(_OTEL_ENVIRONMENT)}\n"
        f"metrics_exporter = {json.dumps(_EXPORTER_OFF)}\n"
        "\n"
        "[otel.trace_exporter.otlp-http]\n"
        f"endpoint = {json.dumps(traces_endpoint)}\n"
        f"protocol = {json.dumps(_HTTP_PROTOCOL)}\n"
        "\n"
        "[otel.span_attributes]\n"
        f"{json.dumps(_WORK_ITEM_ATTR)} = {json.dumps(work_item_id)}\n"
        f"{json.dumps(_DISPATCH_ATTR)} = {json.dumps(dispatch_id)}\n"
    )


def codex_otel_prepare_steps_block(*, codex_otel_config: str | None) -> str:
    """Render the Codex-telemetry `[[run.prepare.steps]]` block.

    Empty string when `codex_otel_config` is None. Writes the projected
    `[otel]` table to `$CODEX_HOME/config.toml` before the agent nodes start,
    which is the ONLY surface codex-core reads its OTLP exporters from.

    Mirrors the sibling credential step deliberately: the body rides the
    container-level env table and the step `printf %s`-es it into place, then
    READS IT BACK with `test -s`, so a projection that silently produced an
    empty file aborts the run HERE rather than surfacing as an unexplained
    telemetry absence at the destination days later — which is the exact
    failure shape this work-item exists to close.

    Mode 600 matches that sibling step. The body carries no secret (no
    exporter headers are set), but `$CODEX_HOME` is a credential directory and
    a uniform mode is one less thing to reason about.
    """
    if codex_otel_config is None:
        return ""
    script = (
        f'mkdir -p "$CODEX_HOME" && printf %s "${CODEX_OTEL_CONFIG_ENV_VAR}" >'
        ' "$CODEX_HOME/config.toml" && chmod 600 "$CODEX_HOME/config.toml"'
        ' && test -s "$CODEX_HOME/config.toml"'
    )
    lines = [
        "",
        "# --- Dispatcher-materialized Codex telemetry projection: write the",
        "# --- [otel] table codex-core reads its trace exporter from ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"


def codex_otel_env_lines(*, codex_otel_config: str | None) -> str:
    """Render the `CODEX_OTEL_CONFIG_TOML` env-table line.

    Empty string when `codex_otel_config` is None. `json.dumps`-ed so the
    multi-line TOML body single-line-encodes with `\\n` escapes (valid TOML),
    exactly like the `CODEX_AUTH_JSON` snapshot beside it.
    """
    if codex_otel_config is None:
        return ""
    return f"{CODEX_OTEL_CONFIG_ENV_VAR} = {json.dumps(codex_otel_config)}\n"
