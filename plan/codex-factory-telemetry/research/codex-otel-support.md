# Research — can Codex (`@zed-industries/codex-acp@0.16.0`) emit OpenTelemetry?

**Read-only investigation, 2026-07-12.** Pinned to `zed-industries/codex-acp@v0.16.0`
and the codex it vendors, `openai/codex@rust-v0.137.0`. Nothing was edited, branched,
or dispatched. This note selects the approach for the parent thread
(`plan/codex-factory-telemetry/`) and is the evidence behind ledger epic
`bd-ib-98c` ("Codex-era factory telemetry").

## Headline verdict: `no-native-otel` (for the adapter as shipped)

`@zed-industries/codex-acp@0.16.0` does **not** honor `OTEL_EXPORTER_OTLP_ENDPOINT` /
`OTEL_EXPORTER_OTLP_PROTOCOL` / `OTEL_TRACES_EXPORTER` / `OTEL_SERVICE_NAME`, and it
**never initializes the OpenTelemetry provider** — so it emits nothing, regardless of
the `OTEL_*` env the sandbox already sets. Two independent, each-fatal reasons:

1. **The adapter binary never wires OTel.** `codex-acp`'s `run_main` installs only a
   plain `tracing_subscriber::fmt()` subscriber; it never calls codex-core's
   `build_provider(...)`. The `codex-otel` crate appears only as a transitive
   `Cargo.lock` entry, never referenced in the adapter's own source (the same
   fmt-only posture fabro has).
2. **Even codex proper is `config.toml`-driven, not `OTEL_*`-env-driven.** codex-core
   resolves its OTLP endpoint/protocol/headers exclusively from the `[otel]` section
   of `~/.codex/config.toml`. The only `OTEL_*` env vars codex reads are the
   **timeout** family (`OTEL_EXPORTER_OTLP_TIMEOUT` / `_TRACES_` / `_LOGS_`).
   `OTEL_EXPORTER_OTLP_ENDPOINT` and the exporter/service-name envs are ignored.

Underneath the gap, codex-core *has* a capable OTel stack (`codex_otel`: logs + traces
+ metrics, OTLP-HTTP JSON **or** protobuf, session-scoped events incl. token usage) —
it is simply never turned on in the ACP path. And the ACP event stream the factory
already rides **does carry token usage + turn lifecycle**, which is the pragmatic emit
seam.

## Evidence (each cited)

- **Adapter pins codex at `rust-v0.137.0`.** `codex-acp` `Cargo.toml@v0.16.0`: every
  `codex-*` dep is `{ git = "https://github.com/openai/codex", tag = "rust-v0.137.0" }`.
- **Adapter installs fmt-only subscriber, no provider.** `codex-acp`
  `src/lib.rs@v0.16.0` L27–32:
  `tracing_subscriber::fmt().with_env_filter(EnvFilter::from_default_env()).init()`.
  No `build_provider`, no `OtelSettings`, no `otel` in `src/*.rs` (only in `Cargo.lock`,
  transitive via codex-core).
- **codex endpoint comes from config, not env.**
  `codex-rs/otel/src/provider.rs@rust-v0.137.0` builds the exporter with
  `.with_endpoint(endpoint)` where `endpoint` is from `OtelConfig` (config.toml).
  `codex-rs/otel/src/otlp.rs` reads env only for timeouts. No
  `OTEL_EXPORTER_OTLP_ENDPOINT` read.
- **`[otel]` config schema.** `codex-rs/config/src/types.rs@rust-v0.137.0`:
  `OtelConfigToml { log_user_prompt, environment, exporter, trace_exporter,
  metrics_exporter, span_attributes, tracestate }`;
  `OtelExporterKind::OtlpHttp { endpoint, headers, protocol }`;
  `OtelHttpProtocol::{Binary, Json}`. `metrics_exporter` defaults to **Statsig**
  (OpenAI's own endpoint); logs/traces default to **None**
  (`codex-rs/core/src/config/otel.rs` `resolve_config`).
- **`service.name` is a `build_provider` argument, not a config/env key.**
  `codex-rs/core/src/otel_init.rs@rust-v0.137.0`:
  `build_provider(config, service_version, service_name_override, …)`,
  `service_name = service_name_override.unwrap_or(originator.value)`. So "just set a
  `service.name`" is impossible without a code path that calls `build_provider`.
  `codex_export_filter` also restricts OTLP export to `codex_otel`-targeted events.
- **Non-interactive paths are known-dark upstream.** openai/codex issue **#12913**
  (2026-02-26, codex-cli 0.105.0): interactive CLI = traces+logs+metrics;
  `codex exec` = traces+logs, no metrics; `codex mcp-server` = **zero OTel, never
  initializes the provider**. The ACP adapter is a sibling non-interactive/server
  entry point with the same "provider never initialized" shape.
- **The ACP stream DOES carry token usage + turn lifecycle.** `codex-acp`
  `src/thread.rs@v0.16.0`: `EventMsg::TokenCount(TokenCountEvent{ info, .. })` →
  `SessionUpdate::UsageUpdate(…tokens_in_context_window…)` (≈L1128–1132);
  `EventMsg::TurnComplete(TurnCompleteEvent{ turn_id, duration_ms,
  time_to_first_token_ms, .. })` (≈L1351); `ThreadGoalStatus::UsageLimited`.
  **Caveat:** `UsageUpdate` is context-window occupancy, not a cumulative
  input/output/cached token *cost* breakdown — that richer accounting lives in
  codex-core's `SessionTelemetry`, reachable only via the native provider path.

## Approach selected: **Approach 2 (fabro-side OTLP from the ACP handler)** first

Approach 1 as originally framed ("Codex honors `OTEL_*` → one `service.name` + a
protocol check away") is **falsified** — it depends on an env-honored endpoint AND an
auto-initialized provider, both false.

- **Primary — Approach 2.** Emit orchestration + node-lifecycle + agent-turn spans
  from fabro's ACP handler (`fabro-workflow/src/handler/llm/acp.rs`, its
  `Emitter`/`RunNotice` surface) via the **fabro-side OTLP exporter already tracked as
  `bd-ib-i4r`** (uncommitted in the stale `~/.worktrees/fabro/instrument-v0254` fork;
  must be re-derived vs current main). No dependency on codex-acp source changes; rides
  an in-flight enabler; covers the layer the factory most needs (which node/turn ran,
  tool calls, notices, outcomes, TTFT, duration) plus a **coarse token signal** from the
  ACP `UsageUpdate`/`TurnComplete` events. The honest near-term unblock.
- **Optional follow-on — native codex telemetry** (only if Codex-internal token/cost
  fidelity is required — the `total_usd_micros` gap tracked in
  `livespec-impl-beads-zbl`): (a) an upstream/fork change to `codex-acp` `run_main` that
  calls `codex_core::otel_init::build_provider(config, version, Some("codex"), …)` and
  installs the returned layers (mirror `codex-rs/mcp-server/src/lib.rs`), AND (b)
  provisioning `~/.codex/config.toml [otel]` per sandbox with `trace_exporter`/`exporter`
  = `otlp-http { endpoint = "http://172.17.0.1:4318", protocol = "json" }`. Higher
  fidelity, but gated on an upstream PR we don't control (or carrying a fork) plus a
  per-sandbox config step — a second increment.

## Ready build steps (to be groomed into dependency-layered children of `bd-ib-98c`)

Approach-2 spine (do first):
1. **Confirm fabro's OTLP wire format + endpoint** with the `fabro-token-refresh` track
   / `bd-ib-i4r`: `http/protobuf` (Rust default) or `http/json`? Endpoint must be the
   sandbox→host `http://172.17.0.1:4318`. Verifiable: capture one POST's `Content-Type`
   at the receiver.
2. **Teach `_otel_receive.py` `http/protobuf`** IF step 1 says protobuf. Verifiable by a
   unit test decoding a protobuf `ExportTraceServiceRequest` into the same ingested-span
   shape the JSON path produces.
3. **Emit fabro node/turn spans** from the ACP handler: one span per dispatched node +
   child spans per ACP turn/tool-call, carrying the correlation triple
   (`service.namespace=livespec-family`, `work.item.id`, `livespec.dispatch.id`) already
   injected via `OTEL_RESOURCE_ATTRIBUTES`. Pick a `service.name` (e.g. `codex-agent` or
   `fabro`) and add its `honeycomb_dataset_for` mapping in `_otel_enrich.py`. Verifiable:
   one dispatch produces a trace in the chosen Honeycomb dataset.
4. **Map ACP `UsageUpdate` + `TurnComplete` → span attributes/metrics** (context-window
   tokens, TTFT, turn duration). Verifiable: attributes present on the turn spans.
5. **Content-redaction pass** mirroring the CC "content-flags-off" hygiene — assert no
   prompts / tool I/O / raw bodies leave the sandbox unredacted (route through
   `_otel_scrub.py`). Verifiable by a scrub unit test over a sample event.

Native-codex follow-on (later increment, only if pursued):
6. **Spike: fork/PR `codex-acp` `run_main`** to call
   `build_provider(config, env!("CARGO_PKG_VERSION"), Some("codex"), …)` and install the
   returned logger/tracing layers. Verifiable in a throwaway sandbox: codex emits
   `SessionTelemetry` spans.
7. **Provision `~/.codex/config.toml [otel]`** in the sandbox image/overlay with
   `otlp-http { endpoint, protocol = "json" }`, and set `metrics_exporter` off / pointed
   at the receiver instead of the built-in **Statsig** default (else metrics leak to
   OpenAI's `ab.chatgpt.com`). Verifiable: codex token/cost spans arrive; nothing hits
   `ab.chatgpt.com`.

## Receiver-protocol note

`_otel_receive.py` is **JSON-only** today: `_handle_traces`/`_handle_metrics` call
`read_json_body`; routes are `/v1/traces` + `/v1/metrics` (no `/v1/logs`).

- **Native-codex path:** no protobuf needed — set `protocol = "json"` in `[otel]` and the
  receiver works as-is. (If codex logs are wanted, add a `/v1/logs` route.)
- **Approach-2 (fabro-side):** likely **needs `http/protobuf`** added, because Rust
  `opentelemetry-otlp` HTTP exporters default to protobuf and often aren't compiled with
  JSON. So step 2 is probably load-bearing — confirm with `bd-ib-i4r` (step 1) before
  building. Adding protobuf is the right fix rather than forcing fabro into a
  rarely-supported JSON mode.

## Open questions / coordination

- **`fabro-token-refresh` / `bd-ib-i4r` alignment (blocks step 1):** agree on wire
  format (json vs protobuf → drives receiver work), `service.name`/dataset naming, and
  that both emitters carry the same correlation triple so fabro (orchestration) and
  codex (agent, if native later) spans join.
- **Statsig default (maintainer decision, native path only):** codex's
  `metrics_exporter` defaults to **Statsig → `https://ab.chatgpt.com/otlp/v1/metrics`**.
  Any native-path work must explicitly override it, or codex metrics egress to OpenAI.
  Not a concern for Approach 2.
- **Token-cost fidelity:** Approach 2's ACP `UsageUpdate` gives context-window occupancy,
  not a full input/output/cached cost breakdown. If `total_usd_micros` needs true cost,
  that requires the native `SessionTelemetry` path (steps 6–7). Decision for the
  maintainer: is coarse-now + rich-later acceptable?
- **Adapter version drift:** findings are pinned to `codex-acp@0.16.0` / codex
  `rust-v0.137.0`. Upstream is actively closing these gaps (cf. issue #12913) — re-check
  on any `CODEX_IMPLEMENTER_ADAPTER` bump before committing to the fork path.

Files referenced (all under `livespec-orchestrator-beads-fabro`):
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_receive.py`,
`_otel_enrich.py`, `_otel_scrub.py`, `_dispatcher_plan.py`, `_dispatcher_cost.py`.
