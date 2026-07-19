# Codex-era factory observability gap — reasoning

## The problem in one paragraph

The dark-factory's telemetry pipeline was built around **Claude Code's
native OpenTelemetry**. It has gone dark for every run since ~2026-06-13
because the factory now drives its implementer/PR/review work with
**Codex** (the `@zed-industries/codex-acp` ACP adapter), and Codex emits
none of the telemetry the pipeline is wired to capture. We are therefore
**blind on every current production run** in Honeycomb.

## Evidence (ground truth, 2026-07-09)

Honeycomb env `livespec` (team `thewoolleyweb`), datasets and their last
event:

| dataset | newest event | meaning |
| --- | --- | --- |
| `github-ci` | current (2026-07-09) | CI — healthy, proves Honeycomb ingest works |
| `claude-code` | ~2026-06-13 | CC sandbox telemetry — DARK |
| `livespec-dispatcher` | ~2026-06-13 | dispatcher spans — DARK (272 spans total, ever) |
| `fabro-sandbox` | ~2026-06-13 | DARK (31 spans total, ever) |
| `claude-subagents`, `livespec-rgr`, `livespec-smoketest` | ~2026-06-13 | DARK |

So the ingest key and Honeycomb side are fine; the **emitter** stopped.

## Why it went dark — the mechanism

1. The "29f" telemetry epic (early June) wired a pipeline that is
   **Claude-Code-native**. `_dispatcher_plan.py:cc_otel_overlay_env()`
   projects into the sandbox: `CLAUDE_CODE_ENABLE_TELEMETRY=1`,
   `OTEL_{METRICS,LOGS,TRACES}_EXPORTER=otlp`,
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://172.17.0.1:4318`,
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, and the correlation triple
   in `OTEL_RESOURCE_ATTRIBUTES` (`service.namespace=livespec-family`,
   `work.item.id`, `livespec.dispatch.id`). `service.name` is left at
   CC's own `claude-code`.
2. Only **Claude Code** honors `CLAUDE_CODE_ENABLE_TELEMETRY` and self-
   instruments to emit those signals. The current implementer/PR/review
   nodes run on the **Codex ACP adapter**
   (`_dispatcher_plan.py:CODEX_IMPLEMENTER_ADAPTER =
   "npx -y @zed-industries/codex-acp@0.16.0"`). Codex honors none of
   the `CLAUDE_CODE_*` knobs and does not emit OTLP on its own.
3. **fabro itself emits no OpenTelemetry** at v0.254.0 (verified: no
   `opentelemetry*` crates in `Cargo.lock`; `fabro-cli/src/logging.rs`
   installs a `tracing` **fmt-only** subscriber; "fabro-telemetry" is
   Segment analytics + Sentry crash reporting, not tracing). So fabro
   never filled the gap either. The `fabro-sandbox` dataset's 31 spans
   were almost certainly a short-lived June experiment, not stock fabro.

Net: the sandbox has the standard `OTEL_*` env pointed at a live
receiver, but nothing inside it emits.

## What is already intact and reusable (the good news)

The **receive + egress plane is healthy and armed on every dispatch** —
only the emitter is missing:

- Host-local OTLP/HTTP **receiver**: `commands/_otel_receive.py`,
  default **port 4318**, started fail-open at dispatch entry
  (`dispatcher.py:_ensure_otel_receiver`, called at the real dispatch
  entry points).
- **Enrich + scrub + egress**: `commands/_otel_enrich.py`,
  `commands/_otel_scrub.py`; the Honeycomb ingest key
  (`HONEYCOMB_INGEST_KEY_LIVESPEC`) is added **host-side** at egress —
  the sandbox ships plaintext to `172.17.0.1:4318`.
- **Sandbox→host endpoint**: `172.17.0.1:4318` (Docker bridge gateway),
  `_dispatcher_plan.py:DEFAULT_SANDBOX_OTEL_ENDPOINT`.
- **Correlation triple** already defined and injected.

Any emitter in the sandbox that ships OTLP/HTTP to `172.17.0.1:4318`
will flow straight through to Honeycomb.

## Approach options (decide in the driving session)

1. **Native Codex OTel (cheapest if it exists).** Investigate whether
   `@zed-industries/codex-acp@0.16.0` and/or `codex-core` honor standard
   `OTEL_*` env or have any telemetry export. The container-level
   `OTEL_EXPORTER_OTLP_ENDPOINT` is already set; if Codex honors it, the
   remaining work is a `service.name` for a `codex` dataset + verifying
   protocol (the 29f receiver is JSON-only today — confirm Codex speaks
   `http/json`, or teach the receiver `http/protobuf`).
2. **Codex-event → OTLP bridge.** If Codex does not emit: translate the
   ACP event stream (turns, tool calls, notices, outcomes) into OTLP
   spans. fabro's ACP handler (`fabro-workflow/src/handler/llm/acp.rs`)
   already observes these events via its `Emitter`/`RunNotice` surface —
   so a **fabro-side OTLP exporter** (see the token-refresh track, which
   is adding OTLP export to fabro anyway) can emit the orchestration +
   node-lifecycle + agent-turn layer without a separate shim. Decide
   whether fabro-side spans are sufficient, or a wrapper around the
   adapter command is also needed for Codex-internal detail.
3. **Token/cost signal.** The dispatcher cost seam
   (`_dispatcher_cost.py`) notes `total_usd_micros` is null on fabro
   runs in v0.254.0, so autonomous mode refuses to keep picking on
   unobservable cost. Codex token/cost telemetry would feed this — a
   concrete high-value target for whatever emitter path is chosen.

## Relationship to the fabro-token-refresh track

The token-refresh track is **adding OTLP export capability to fabro** (a
scope-preserving, upstream-worthy OTel improvement) to debug the >60-min
expired-token bug. That capability is a **shared enabler** for this plan:
it makes fabro's own spans (node lifecycle, credential events, agent
turns) observable, which covers the *orchestration* layer. This plan is
about the *Codex agent* layer on top of that. Coordinate so the two
tracks agree on: the receiver protocol (json vs protobuf), the
`service.name`/dataset naming, and the correlation attributes.

## Open questions

- Does `codex-acp@0.16.0` / `codex-core` emit or forward OTel at all?
- Receiver protocol: keep JSON-only, or add protobuf? (fabro's OTLP
  exporter and Codex may prefer `http/protobuf`.)
- Dataset/service naming for the Codex layer (`codex`, `codex-sandbox`,
  or fold into a `fabro` service with a span attribute?).
- Content redaction: mirror the CC "content-flags-off" hygiene (no
  prompts / tool I/O / raw bodies leave the sandbox unredacted).
