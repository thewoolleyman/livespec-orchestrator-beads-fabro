# O2 execution plan — join the server + worker `run` spans via W3C traceparent (bd-ib-98c.5)

**Execution-ready build plan for O2**, the second slice of the outward fabro emitter
spine. Grounded in fresh code verification on `factory-integration` (2026-07-17, tip
`c543446`, which already carries O1/Lever B). Companion to `handoff.md`,
`emitter-replan.md`, and `o1-worker-exporter-plan.md`.

## Why O2

O1 is PROVEN: a real dispatch emits **two** root `run` spans to Honeycomb — one from the
host server, one from the `__run-worker` subprocess — in **two distinct trace IDs**
(`service.name=fabro`). They describe the same run but are disconnected, so you cannot
see the whole run as one trace. O2 joins them: the server propagates its run-span
context to the worker as a W3C `traceparent`, and the worker parents its run span on it —
yielding **one** trace per dispatch.

## The two seams (verified on `factory-integration`)

- **Server run span (inject side):** `lib/crates/fabro-server/src/server.rs:4339` —
  `execute_run(state_clone, id).instrument(tracing::info_span!("run", id = %id))`. Inside
  this instrumented future the run span is `Span::current()`.
- **Worker run span (extract side):** `lib/crates/fabro-cli/src/commands/run/mod.rs:96` —
  `let run_span = tracing::info_span!("run", id = %run_id); … .instrument(run_span)`.
  `set_parent` slots cleanly between the `info_span!` and the `.instrument(run_span)`.
  **Also handle the Resume arm** (`run/mod.rs:~109 RunCommands::Resume`), which re-enters
  a worker run span on the parked-run path — check for a run-span creation there and
  parent it identically, or O2 only joins Start-path runs.
- **Env carrier seam:** `lib/crates/fabro-server/src/worker_runtime.rs:89-103` — the same
  block O1 uses. O2 adds one more `cmd.env(...)`, but the VALUE is per-run dynamic (the
  run's traceparent), NOT static config — see below.

## Dependencies already present

`Cargo.toml`: `opentelemetry = "0.30"`, `opentelemetry_sdk = "0.30"`,
`tracing-opentelemetry = "0.31"`. That is the whole API surface O2 needs — **no new
dependency**. There is currently **no** propagation/`traceparent`/`OpenTelemetrySpanExt`
usage anywhere in fabro (verified), so O2 introduces it cleanly.

## Design

### Server side — capture + inject (per run)

1. In `execute_run` (server.rs, where the `run` span is current), capture the run-span
   OTel context and serialize it to a W3C `traceparent`:
   - `use tracing_opentelemetry::OpenTelemetrySpanExt;`
   - `let cx = tracing::Span::current().context();`
   - `let mut carrier = std::collections::HashMap::<String, String>::new();`
   - `opentelemetry_sdk::propagation::TraceContextPropagator::new().inject_context(&cx, &mut carrier);`
     (verify the exact import path for `TraceContextPropagator` in 0.30; `HashMap<String,
     String>` implements the `Injector` trait via opentelemetry's blanket impl — confirm.)
   - `let traceparent = carrier.get("traceparent").cloned();`
2. **Thread it explicitly, do NOT re-read `Span::current()` deep in the spawn path.** Add
   a field to `WorkerLaunchSpec` (e.g. `traceparent: Option<String>`) and populate it in
   `execute_run` where the run span is unambiguously current. `worker_runtime` then reads
   `spec.traceparent` — this avoids losing the span across any `tokio::spawn` boundary
   between `execute_run` and the worker launch.
3. In `worker_runtime.rs` (the O1 block at :89-103), inject it:
   `if let Some(tp) = spec.traceparent.as_deref() { cmd.env("TRACEPARENT", tp); }`
   `TRACEPARENT` is the W3C/OTel env convention. It is non-secret (trace/span IDs only),
   so unlike the OTLP headers it is safe in the worker.

### Worker side — extract + set_parent

At `run/mod.rs:96`, between the `info_span!` and the `.instrument(run_span)`:
- `use tracing_opentelemetry::OpenTelemetrySpanExt;`
- read `TRACEPARENT` from env into a one-key carrier `HashMap<String,String>`;
- `let parent_cx = TraceContextPropagator::new().extract(&carrier);`
- `run_span.set_parent(parent_cx);`

Now the worker's run span is a child of the server's run span → one joined trace.

## Guardrails (make O2 a no-op when export is off)

- **Invalid/empty context ⇒ no injection.** When `otel_layer()` returns `None` (no OTLP
  endpoint configured — Lever A env absent), the OpenTelemetry layer is not installed, so
  `Span::current().context()` has no valid remote span context and `inject_context`
  produces no usable `traceparent`. Guard: only `cmd.env("TRACEPARENT", …)` when the
  captured value is present and non-empty. On the worker, an absent/empty/invalid
  `TRACEPARENT` must leave the run span as a root (today's behavior) — `extract` of an
  empty carrier yields an empty context and `set_parent` of it is harmless, but verify
  it does not attach an invalid parent. O2 must never change behavior when export is off.
- **No secret exposure.** `traceparent` carries only W3C trace/span IDs + flags — no
  credential. It is safe in the sandboxed worker (unlike `OTEL_EXPORTER_OTLP_HEADERS`,
  which O1 deliberately strips and O2 does not touch).

## What O2 does NOT do

- No new spans (that is O3/O4 — but see the scope note below).
- No token/cost (O5, `bd-ib-98c.8`, deferred).
- Does not alter O1's env forwarding or the headers strip.

## Verification (the gate before calling O2 done)

1. CI-equivalent on `factory-integration`: `fmt --check --all`, `clippy --locked
   --workspace --all-targets -- -D warnings`, tests — all under the pinned
   `nightly-2026-04-14` (the same toolchain O1 used).
2. Rebuild + re-pin the host binary (per `orchestrator-image/README.md`; the O1 cutover
   is the worked example). NOTE: the orchestrator-image rebuild is currently blocked by
   `bd-ib-dwv` (dead beads URL) — the host-direct proof does not need the image, but the
   image stays stale until that is fixed.
3. Proof-dispatch (promote a throwaway item to `ready` — the factory tends to have no
   ready-status work; `bd-ib-dqt` was the O1 example). Then in Honeycomb (`livespec` env,
   `fabro` dataset): the two `run` spans must now share **ONE** `trace.trace_id`, with the
   worker run span's `trace.parent_id` = the server run span's `trace.span_id`. Contrast
   with O1's proven state (2 run spans, 2 trace IDs).
4. Update `bd-ib-98c.5` + `handoff.md`.

## Review criteria (Codex + Fable loops, like O1)

Completeness (both Start and Resume worker arms; guarded when export off); narrow fix;
preserves all fabro APIs; no regression in fabro OR livespec; the `traceparent` is
per-run and never an invalid/stale parent; no secret reaches the worker.

## Scope note — O3/O4 may already be largely covered

O1's proof-dispatch showed the export already carries a rich fabro span tree beyond the
`run` span — `Stage started/completed`, `Edge selected`, `Checkpoint completed`,
`Fidelity resolved`, `Sandbox initialized/ready/stop`, `Setup started/completed`,
`Workflow run started/completed`, `connection` (all in the `fabro` dataset). O3
(node-lifecycle) and O4 (ACP-turn) were planned as new instrumentation, but much of that
layer is **already visible** because fabro's existing tracing tree is deeper than the
emitter re-plan assumed ("one span deep"). Before building O3/O4, re-verify against this
live span set what — if anything — is genuinely missing (e.g. ACP `command`/`stop_reason`/
`visit`/`files_touched` attributes on `run_turn`), and shrink O3/O4 to only that gap.
