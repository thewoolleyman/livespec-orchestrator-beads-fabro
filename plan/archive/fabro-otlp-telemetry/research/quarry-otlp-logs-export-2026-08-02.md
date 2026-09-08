<!--
Snapshot captured: 2026-08-02T02:58:00Z
Rendered source: https://quarry.lithos.computer/tmp/4c799d4a7e164723bc2f416ee06ff580
Markdown endpoint: https://quarry.lithos.computer/v1/tmp/documents/4c799d4a7e164723bc2f416ee06ff580
Source ETag observed at capture: ca670f34-206f-44ee-941a-94218ab41810
Source expiry advertised at capture: 2026-08-24T11:08:39.572Z

This is a local reference snapshot of Bryan's Quarry design. The Markdown
content below matches Quarry's text/markdown response at capture; only this
comment header was added locally.
-->
# OTLP Logs Export

Export Fabro run events to an OpenTelemetry endpoint over OTLP/HTTP.

**Scope: logs only.** Metrics and traces are explicitly deferred (see [Non-goals](#non-goals)).

## Goal

An operator configures an OTLP endpoint and every canonical `RunEvent` — `run.created`, `stage.completed`, `agent.llm.started`, `sandbox.ready`, all \~130 of them — arrives at their observability backend as a structured OTLP log record, with the same envelope and the same redaction as the run store, SSE stream, and `fabro dump` bundle.

Off by default. No built-in destination, no vendor endpoint compiled into the binary, no traffic without an explicitly configured endpoint.

## Design

### RunEvent → OTLP, not tracing → OTLP

The obvious implementation is `opentelemetry-appender-tracing`: add a layer to the subscriber and every `info!`/`debug!` in the workspace becomes an OTLP log record. We are not doing that.

`docs/internal/logging-strategy.md:7` defines tracing output as "for **developers debugging issues after the fact** — they are not user-facing output." Levels, messages, and fields are deliberately unstable; the prohibited-fields table (`logging-strategy.md:199-230`) is enforced by review, not by types. Shipping that firehose to a third party turns an intentionally-unstable developer artifact into an external contract.

Both reference implementations reached the same conclusion and curate instead:

- **Codex** filters its appender layer to a dedicated target prefix (`codex-rs/otel/src/targets.rs`, `provider.rs:157-161`). Only events emitted through the `log_event!` macro — which stamps a fixed metadata envelope — are exported. `tracing` is transport; the telemetry surface is separate.
- **Claude Code** publishes a closed catalog of 15 named log events, each with a documented attribute list.

Fabro already has that curated surface, and it is better developed than either reference's: `RunEvent` has a canonical envelope, dot-named variants, a documented 7-step process for adding one (`docs/internal/events-strategy.md`), and redaction on the way out. `events-strategy.md:19` already reserves a fanout slot for exactly this.

So: **`RunEvent` is our `log_event!`.** The OTLP exporter is a new sink alongside the store, JSONL, and SSE sinks.

Consequence worth noting: **phase 1 does not touch `lib/apps/fabro-cli/src/logging.rs` at all.** No subscriber layer, no `opentelemetry-appender-tracing`, no `tracing-opentelemetry`. The provider is standalone and the sink calls the Logs API directly. That removes the largest source of risk from the change.

### Record mapping

One `RunEvent` → one OTLP `LogRecord`.

| OTLP field | Source |
| --- | --- |
| `Timestamp` | `RunEvent::ts` |
| `ObservedTimestamp` | emit time |
| `EventName` | `"fabro." + RunEvent::event_name()` → `fabro.run.created` |
| `SeverityNumber` / `SeverityText` | derived, see below |
| `Body` | redacted `properties`, as a structured `AnyValue` map |
| Attributes | envelope fields, see below |

**Attributes** (envelope only — bounded, \~12 keys, all low-cardinality except the ids):

`fabro.run_id`, `fabro.stage_id`, `fabro.node_id`, `fabro.node_label`, `fabro.parallel_group_id`, `fabro.parallel_branch_id`, `fabro.session_id`, `fabro.parent_session_id`, `fabro.tool_call_id`, `fabro.event.id` (the ULID/UUIDv7, for dedup), plus actor projection `fabro.actor.kind` and the variant-specific `fabro.actor.*` fields.

Optional fields are omitted, never emitted as null — matching the envelope rule in `events-strategy.md`.

**Resource attributes:** `service.name` (`fabro-server` / `fabro-worker` / `fabro-cli`), `service.version`, `deployment.environment`, `host.name`, plus any operator-supplied `OTEL_RESOURCE_ATTRIBUTES`.

**Severity:** default `INFO`. `WARN` for `run.notice` with `level = "warn"`. `ERROR` for the failure family (`run.failed`, `stage.failed`, `sandbox.failed`, `watchdog.timeout`, `mcp.failed`, `run.pair.failed`, …) and `run.notice` with `level = "error"`. Implemented as a match arm alongside `event_name()` so a new variant that forgets to pick a severity is a compile error, not a silent INFO.

**Body sizing.** Some properties are large (agent messages, exec output tails). The body is serialized with a configurable cap (default 64 KiB); on overflow the body is replaced with a truncated form and `fabro.properties.truncated = true` is set. Promoting a curated allowlist of high-value scalar properties (model, token counts, duration) into queryable *attributes* is follow-up work, not phase 1 — see [Decisions](#decisions).

## The `fabro-otel` crate

New crate at `lib/foundation/fabro-otel/`.

### Layering

`fabro-otel` depends on `fabro-types` (for `RunEvent`), `fabro-static` (`EnvVars`), and `fabro-config` types. It must **not** depend on `fabro-workflow` — foundation crates do not depend on components. The sink is therefore assembled at the composition roots, which already own both halves.

```
fabro-types ──┐
fabro-static ─┼──> fabro-otel ──> (composition roots: fabro-server, fabro-cli)
fabro-config ─┘
```

### Dependencies

```toml
opentelemetry = { version = "0.32", default-features = false, features = ["logs"] }
opentelemetry_sdk = { version = "0.32", default-features = false, features = ["logs", "rt-tokio"] }
opentelemetry-otlp = { version = "0.32", default-features = false, features = [
    "logs", "http-proto", "http-json", "reqwest-client", "reqwest-rustls",
] }
opentelemetry-semantic-conventions = "0.32"
```

Declared in `[workspace.dependencies]` in the root `Cargo.toml` alongside the existing `tracing` entries.

`default-features = false` matters: `opentelemetry-otlp`'s defaults pull in `trace`, `metrics`, and `reqwest-blocking-client`. We want none of those.

**Transitive cost.** `opentelemetry-otlp` 0.32 depends on `reqwest ^0.13.1` — the same major `fabro-http` already uses, so no additional reqwest copy. New in the tree: `prost` 0.14 (required by `http-proto`) and `opentelemetry-http`. No `tonic` — gRPC is out of scope.

### Public API

```rust
pub struct OtelSettings {
    pub service_name:     String,
    pub service_version:  String,
    pub environment:      String,
    pub logs_exporter:    Option<OtlpHttpExporter>,
    pub resource_attributes: BTreeMap<String, String>,
    pub max_body_bytes:   usize,
}

pub struct OtlpHttpExporter {
    endpoint: String,
    headers:  HashMap<String, String>, // resolved; see Configuration
    protocol: OtelHttpProtocol,        // Binary (protobuf) | Json
}

pub struct OtelProvider { /* holds SdkLoggerProvider + Logger */ }

impl OtelProvider {
    /// Returns `Ok(None)` when no exporter is configured — the disabled path
    /// allocates nothing and installs no globals.
    pub fn from(settings: &OtelSettings) -> Result<Option<Self>, OtelError>;

    /// Emit one run event. Non-blocking; the SDK batches internally.
    /// Redaction happens inside — see Redaction.
    pub fn emit_run_event(&self, event: &RunEvent);

    pub fn force_flush(&self);
    pub fn shutdown(&self);
}
```

`Drop` calls `shutdown()`, mirroring `codex-rs/otel/src/provider.rs:196-207`.

## Configuration

### TOML

```toml
[server.otel]
environment = "prod"                       # resource attribute; default "dev"

[server.otel.logs]
exporter = "otlp-http"                     # "none" (default) | "otlp-http"
endpoint = "http://localhost:4318/v1/logs"
protocol = "binary"                        # "binary" (protobuf, default) | "json"
max_body_bytes = 65536

[server.otel.logs.headers]
authorization = "Bearer {{ env.OTLP_TOKEN }}"   # InterpString — see Secrets
```

New `ServerOtelLayer` / `ServerOtelLogsLayer` in `lib/foundation/fabro-config/src/layers/server.rs`, added to `ServerLayer` alongside `logging` (`layers/server.rs:34`), following the `ServerLoggingLayer` shape at `layers/server.rs:193-201`. Header values are `InterpString`, matching LLM provider `extra_headers`, so literal secrets never need to appear in `settings.toml`.

`defaults.toml` gets no `[server.otel]` section. Absent config means disabled — the same way `[server.logging].destination` is intentionally omitted.

### Env overrides

Resolved explicitly in a `fabro-config` function mirroring `resolve_log_destination` (`lib/foundation/fabro-config/src/logging.rs:5-23`), not by letting the SDK read the environment itself. Explicit resolution is testable without mutating process env — which `server-secrets-strategy.md:14` bans workspace-wide, tests included.

| Variable | Overrides |
| --- | --- |
| `OTEL_LOGS_EXPORTER` | `exporter` (`otlp` \| `none`) |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | `endpoint` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `endpoint` (signal-generic; `/v1/logs` appended) |
| `OTEL_EXPORTER_OTLP_LOGS_PROTOCOL` | `protocol` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `protocol` (signal-generic) |
| `OTEL_EXPORTER_OTLP_HEADERS` | `headers` |
| `OTEL_RESOURCE_ATTRIBUTES` | merged into resource attributes |
| `OTEL_SERVICE_NAME` | `service_name` |

Signal-specific wins over signal-generic, matching the OTel spec and Claude Code's precedence. All names added to `fabro_static::EnvVars`.

### Secrets

The header map is `InterpString`, modeled directly on LLM provider `extra_headers` — same shape, same resolution, precedent at `lib/foundation/fabro-auth/src/resolve.rs:376-378`. Two namespaces apply: `{{ env.NAME }}` reads the process environment and `{{ secrets.NAME }}` reads the vault, both at consumption time. Either works; the operator picks.

This is the generic settings interpolation mechanism, not a `ServerSecrets` field, so `server-secrets-strategy.md`'s bootstrap rules do not apply. See that doc's *Settings-declared credentials* section.

Resolution happens once, in the server. The resolved header values — credential included — are then passed to workers as `OTEL_*` env vars. Rationale is in the Worker subprocesses section below.

## Wiring

### Composition roots

Two places construct a `RunEventSink`:

| Site | Current | Becomes |
| --- | --- | --- |
| `lib/apps/fabro-server/src/server.rs:4113` (server process) | `RunEventSink::store(run_store.clone())` | `RunEventSink::fanout(vec![store, otel_sink])` |
| `lib/apps/fabro-cli/src/commands/run/runner.rs:155` (worker subprocess) | `map(stamp_system_worker, fanout([backend, callback]))` | same, with `otel_sink` added to the inner fanout |

Both roots are server-side: the server process and the per-run worker it spawns. There is no CLI-local run execution — `runner.rs` is `RunCommands::RunWorker` and requires `FABRO_WORKER_TOKEN` (`run/mod.rs:84-101`).

The OTLP sink is an ordinary `RunEventSink::callback`, so the `RunEventSink` enum needs no new variant and `fabro-workflow` gains no OTel dependency:

```rust
let otel_sink = RunEventSink::callback(move |event| {
    provider.emit_run_event(&event);
    async { Ok(()) }
});
```

`RunEventLogger` (`event/sink.rs:160-201`) already runs sinks on a dedicated task behind an unbounded channel, so emission is off the workflow hot path for free.

### Worker subprocesses

The server resolves the full OTel configuration once — from TOML plus `OTEL_*` env overrides, including `InterpString` header resolution — and then boots each worker with the resolved values as standard `OTEL_*` env vars. Endpoint, protocol, exporter, resource attributes, service name, and headers including any credential. Set in `apply_worker_env` (`lib/apps/fabro-server/src/spawn_env.rs`) via `Command::env`, which is unaffected by `WORKER_ENV_ALLOWLIST` — that governs what the child *inherits*, not what the parent sets explicitly. No allowlist change is needed.

The worker reads its OTel config from env only. One resolution point, no settings reload, no vault dependency, and provider construction is free to happen at process start when metrics and traces land. Resource attribute `service.name = "fabro-worker"` distinguishes worker records from parent-side ones.

The credential travels in env like everything else, deliberately. Two reasons:

- **Proportionality.** That boundary already carries stronger credentials. `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are allowlisted into the worker (`spawn_env.rs:41-43`) and are *not* removed by the Local sandbox's filter — `LocalSandbox::should_filter_env_var` (`lib/components/fabro-sandbox/src/local.rs:157-167`) matches the suffix `_api_key`, not `_key`, so `aws_secret_access_key` reaches model-generated Bash commands today. An OTLP header is a write-only telemetry ingest credential; treating it more strictly than static cloud keys would be incoherent.
- **No fifth mechanism.** This boundary already has four overlapping partial controls — `WORKER_ENV_ALLOWLIST`, `ENV_SAFELIST`, the `should_filter_env_var` suffix heuristic, and the `FABRO_WORKER_TOKEN` startup scrub. Adding a scrub or a parallel vault path for a weaker credential adds surface without adding safety.

For reference, what actually inherits worker env: Local sandbox exec **does** (filtered by the suffix heuristic above); Docker and Daytona sandboxes **do not**, since commands run in the container; MCP stdio servers **do** unless `clear_env = true`, which defaults false (`lib/components/fabro-mcp/src/client.rs:58`); non-sandbox hooks **do**, with no `env_clear()` at all (`lib/components/fabro-hooks/src/executor.rs:260-266`).

If defense in depth is wanted later, the honest one-line version is adding `OTEL_EXPORTER_OTLP_HEADERS` to an explicit deny list in `local.rs` — not a scrub, and not a separate credential channel.

### Flush and shutdown

Ordering matters — flush the event logger first, then shut down the provider:

- Server: on graceful shutdown, after the run event logger drains.
- Worker: before process exit, after the final `run.completed` / `run.failed` is emitted. A dropped provider force-flushes, but relying on `Drop` ordering during process teardown is fragile; call it explicitly.

Failure to reach the endpoint must never fail a run. The SDK's batch processor already drops on error; we log at `warn!` and continue.

## Redaction

Non-negotiable: the OTLP record must carry the **same redacted bytes** as the JSONL and SSE surfaces. `events-strategy.md` requires it, and this is the one path that leaves the operator's trust boundary.

`fabro-otel` owns this rather than trusting the caller. `normalized_event_value`, `redacted_event_value`, and `redacted_event_json` move down from `lib/components/fabro-workflow/src/event/redaction.rs` into `fabro-types::run_event`, and `emit_run_event` redacts internally. `build_redacted_event_payload` and `event_payload_from_redacted_json` stay in `fabro-workflow` because they need `fabro_store::EventPayload`.

The dependency direction is clean: `fabro-redact` has no fabro dependencies at all, `fabro-util` depends only on `fabro-static`, and `fabro-types` already depends on `fabro-util`. So `fabro-types` can take `fabro-redact` with no cycle.

A conformance test asserts byte-parity between the OTLP body and `redacted_event_json` for a fixture event set.

## Testing

Following `docs/internal/testing-strategy.md`:

1. **Unit, `fabro-otel`** — record mapping: envelope→attributes, severity derivation per variant family, `event.name` prefixing, body truncation at the cap, omission of `None` fields.
2. **Unit, `fabro-config`** — env override precedence (signal-specific beats generic), invalid values rejected with a message naming the variable, absent config resolves to disabled. Uses injected env values, never process env.
3. **Disabled path** — `OtelProvider::from` with no exporter configured returns `Ok(None)`, installs no globals, and opens no sockets. Assert no network activity.
4. **Loopback integration** — a local HTTP server accepting OTLP/protobuf on an ephemeral port; drive a scripted run and assert the decoded records. Codex has exactly this at `codex-rs/otel/tests/suite/otlp_http_loopback.rs` (722 LOC) and it is worth mirroring. Client must use `.no_proxy()` per CLAUDE.md.
5. **Redaction parity** — OTLP body equals `redacted_event_json` for a fixture set, including at least one event with an `ExecOutputTail` and one with a credential-bearing URL.
6. **Coverage** — a test asserting every `EventBody` variant has an explicit disposition: a severity mapping, or an explicit *excluded* arm. New variants cannot silently default, and the `TextDelta` / `ToolCallOutputDelta` exclusions stay deliberate rather than becoming omissions.
7. **Worker env transport** — a subprocess test asserting the worker receives the resolved `OTEL_*` variables via `Command::env` and exports with them, using `Command::env` per `server-secrets-strategy.md`'s Tests section rather than mutating process env.

## Phasing

| Step | Deliverable |
| --- | --- |
| 1 | Move redaction helpers down to `fabro-types::run_event`; `fabro-types` takes `fabro-redact`. |
| 2 | `fabro-otel` crate: settings types, `OtelProvider`, record mapping, unit tests. No callers. |
| 3 | `fabro-config`: `[server.otel]` layer, env override resolution, `EnvVars` consts, tests. |
| 4 | Server wiring: provider on startup, sink fanout at `server.rs:4113`, flush on shutdown. |
| 5 | Worker wiring: resolved `OTEL_*` into `apply_worker_env`, provider per worker, flush before exit. |
| 6 | Loopback integration test, redaction parity test, worker env transport test. |
| 7 | Docs: operator page in `docs/public/`, event catalog reference, `[server.otel]` reference. |

Steps 1–3 are independent of any caller. Step 1 lands first because step 2's `emit_run_event` signature depends on it.

## Non-goals

- **Metrics.** Deferred. When it happens, `Emitter::emit_with_scope` (`event/emitter.rs:102-113`) is the chokepoint and `BillingAccumulator` (`server.rs:4155-4166`) already computes token/cost/timing totals that are currently discarded on restart.
- **Traces.** Deferred. Fabro has 0 `#[instrument]` attributes and 3 manual spans; there is effectively nothing to export. Codex has 78 `#[instrument]` for comparison. This is a span-design project, not a plumbing project.
- **gRPC / OTLP over 4317.** HTTP only. Avoids `tonic` entirely.
- **Any built-in or default destination.** No compiled-in endpoint, no vendor default. Disabled unless an endpoint is configured.
- **Exporting developer `tracing` logs.** Explicitly rejected above.
- **`tracing-opentelemetry` / `opentelemetry-appender-tracing`.** Not needed for this phase.

## Decisions

1. **Worker transport.** The server resolves the full OTel configuration from TOML plus `OTEL_*` env overrides, then boots each worker with the resolved values as standard `OTEL_*` env vars — including headers and any credential. `Command::env` after `env_clear()` is unaffected by `WORKER_ENV_ALLOWLIST`, so no allowlist change is needed. The worker reads env only: one resolution point, no settings reload, no vault dependency, and provider construction can move to process start when metrics and traces land. Rationale in [Worker subprocesses](#worker-subprocesses).
2. **Exporter type.** `Option<OtlpHttpExporter>`, not a two-variant enum. Absence is the only other state, which `Option` already encodes, and it makes "disabled but an endpoint is configured" unrepresentable. If gRPC ever lands, `Option` → enum is mechanical.
3. **Attribute promotion.** Deferred. Phase 1 is envelope-to-attributes with redacted properties in the body; promoting high-value scalars (`model`, `input_tokens`, `output_tokens`, `duration_ms`) into queryable attributes is follow-up work.
4. **`event.name` prefix.** Prefixed — `fabro.run.created`, not the bare `run.created` — so Fabro records stay distinguishable when they share a backend with other services.
5. **Redaction helper location.** Moved down to `fabro-types::run_event` so `fabro-otel` owns redaction rather than trusting the caller. See [Redaction](#redaction).
6. **Per-run opt-out.** None. Export is a server-level switch only.
7. **Streaming variants.** Excluded. `TextDelta` and `ToolCallOutputDelta` are dropped at the sink, matching their no-op treatment in `trace()`. The coverage test gets an explicit *excluded* arm so this stays deliberate.

## Follow-ups outside this plan

- `LocalSandbox::should_filter_env_var` (`lib/components/fabro-sandbox/src/local.rs:157-167`) matches the suffix `_api_key` but not `_key`, so `AWS_SECRET_ACCESS_KEY` — allowlisted into the worker at `spawn_env.rs:41-43` — reaches Local-provider sandbox commands. A real latent leak, independent of OTLP, and worth its own issue.
