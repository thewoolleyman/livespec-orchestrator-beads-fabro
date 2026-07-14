<!-- Working draft of the upstream fabro PR body for the OTLP transport
     (bd-ib-i4r). Refined by the Codex + Fable adversarial-review loop before
     the PR is opened. Head: thewoolleyman/fabro:otlp-span-export. Base:
     fabro-sh/fabro:main. Commit: ca59259b1 (may be amended by review fixes). -->

# feat(cli): opt-in OTLP/HTTP export for tracing spans

## Summary

Adds an **opt-in** OTLP/HTTP exporter for fabro's existing `tracing` spans. It is
**additive and inert** unless an OTLP endpoint env var is set — when unset,
`otel_layer()` returns a no-op `None` layer, so the tracing stack is behaviorally
unchanged (the `fmt` layers and their output are untouched) and nothing is
exported. This PR is pure **transport**: it adds **no new instrumentation points**
to fabro's code. When enabled, fabro's existing `tracing` spans — the same span tree
that structures its log output — are bridged to OTLP via the standard
`tracing-opentelemetry` layer (which maps them to OTel using conventional semantics,
e.g. error events → span status). The optional synthetic extras (busy/idle timing,
thread, source location) are disabled, so exported spans stay close to fabro's actual
spans.

## What it does

- New `lib/crates/fabro-cli/src/otel.rs`: builds an `opentelemetry-otlp` span
  exporter + `tracing-opentelemetry` layer, guarded by `OTEL_EXPORTER_OTLP_ENDPOINT`
  / `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. Returns a no-op (`None`) layer when unset.
- `logging.rs`: adds `.with(otel::otel_layer())` alongside the existing `fmt`
  layer in all four subscriber-init paths (cli / server-stdout / worker /
  worker-stdout).
- `main.rs`: registers `mod otel` and calls `otel::shutdown()` late in `main` for a
  best-effort final drain on the normal-exit path (no-op when disabled).
- `fabro-static/src/env_vars.rs`: registers the five `OTEL_*` names as `EnvVars`
  consts (fabro's env-var naming convention), referenced from `otel.rs`.
- Deps: `opentelemetry` / `opentelemetry_sdk` 0.30, `opentelemetry-otlp` 0.30
  (`default-features = false`; `http-proto` + `http-json` + `reqwest-blocking-client`
  — drops the unused OTLP logs exporter), `tracing-opentelemetry` 0.31. The OTLP HTTP
  features enable `metrics` unconditionally, so the trace+metrics SDK is compiled (a
  trace-only reduction isn't achievable via the HTTP exporter). These reuse the
  `reqwest 0.12` already in the lockfile — **no new reqwest version**. The lockfile
  gains `tonic 0.13` + `prost 0.13` transitively (via `opentelemetry-proto`'s protobuf
  message types for `http/protobuf`) — message codegen only; **no gRPC transport** is
  compiled or used.

## Env vars honored

This module resolves the **endpoint** itself (from `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
else `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/traces`) and pins the **protocol**
(per-signal `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` wins, else
`OTEL_EXPORTER_OTLP_PROTOCOL`; default `http/protobuf`, the OTLP spec default; set
`http/json` to switch) and the **service name** (`OTEL_SERVICE_NAME`, default `fabro`).
The `opentelemetry-otlp` exporter reads the remaining OTLP vars itself — **headers**
(`OTEL_EXPORTER_OTLP_HEADERS` / `..._TRACES_HEADERS`) and **timeouts**
(`OTEL_EXPORTER_OTLP_TIMEOUT`). Export is gated on a non-empty resolved endpoint.

## Design / blast radius

- Zero behavior change when disabled: `otel_layer()` returns `None`, which is a no-op
  `tracing` layer; the `fmt` layers and their output are untouched.
- No changes to existing public APIs. `otel` is a private `fabro-cli` module
  (`pub(crate)`); the only call sites are the four subscriber inits and the `main`
  drain. (`fabro-static` gains five additive `EnvVars` consts — new public surface,
  not a change to existing APIs.)
- Env-var NAMES are `fabro_static::EnvVars` consts (the `OTEL_*` set was added there);
  the module-level `#![expect(clippy::disallowed_methods, reason = ...)]` covers only
  the `std::env::var` read mechanism, per fabro's env-var convention.
- Export volume is subject to the same `FABRO_LOG` `EnvFilter` as fabro's log output:
  the OTLP layer sits alongside the `fmt` layer under that filter, so a span below the
  configured level is neither logged nor exported.
- Span drain on exit is **best-effort, and mirrors fabro's existing pattern**:
  `otel::shutdown()` is placed right beside `fabro_telemetry::shutdown()` on the
  normal `main` exit path. fabro's own telemetry shutdown is likewise only on that
  path — its `std::process::exit(...)` bailout sites (preflight, run/*, doctor,
  server/status, …) do not drain `fabro_telemetry` either. Rerouting those sites to
  drain OTLP would make it more aggressive than fabro's own telemetry and touch
  unrelated exit paths; the SDK batch processor exports periodically regardless, so
  such an exit at most drops the last un-flushed batch. (A consistent drain of both
  telemetries on every exit path would be a separate, broader change to fabro's exit
  convention — out of scope for this transport PR.)
- Exporter/provider construction is wrapped in `catch_unwind`: the SDK batch
  processor `expect`s a successful background-thread spawn, so a (near-never)
  spawn failure disables export instead of taking fabro down. The panic still
  passes through fabro's installed panic hook before it is caught, so such a
  failure is reported once and then export is disabled rather than the process
  aborting (`panic = unwind`, so the catch is effective).
- Endpoint handling is fail-safe: the traces endpoint is resolved from the standard
  OTLP env vars (per-signal `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` used as-is, else
  `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/traces`; empty/whitespace treated as unset)
  and passed **programmatically** via `.with_endpoint(...)`. A malformed endpoint
  fails the exporter build and disables export — there is no path where export is on
  while the endpoint silently falls back to localhost. (Delegating to the exporter's
  own env read would silently drop a malformed value and fall back to localhost.)
- Server-spawned workers run under `apply_worker_env`, an env allowlist (env-clear +
  narrow copy) that does not include `OTEL_*`; a server-launched worker therefore
  will not export until those vars are forwarded — a separate decision, since
  `OTEL_EXPORTER_OTLP_HEADERS` can carry secrets. Directly-invoked processes
  (cli / server / `__run-worker`) export normally.
- OTLP export uses `opentelemetry-otlp`'s own internally-built
  `reqwest::blocking::Client`, separate from fabro's `fabro_http` egress facade (so
  it does not consult `FABRO_HTTP_PROXY_POLICY`). This is deliberate for an opt-in
  telemetry exporter that owns its `OTEL_EXPORTER_OTLP_TIMEOUT`-configured client;
  routing OTLP through `fabro_http` (via `.with_http_client(...)`) is a possible
  follow-up if proxy-policy parity is wanted.

## Design decisions

- **Protocol default is `http/protobuf`** — the OTLP spec default. `http/json` is
  available via `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` (both HTTP encodings are
  compiled in).
- **Blocking OTLP client (not the async one).** The SDK's default
  `BatchSpanProcessor` drives the exporter on a dedicated thread via `block_on`, so
  the exporter must not require an ambient async runtime. This PR uses
  `reqwest-blocking-client` (opentelemetry-otlp's own default) — no dependency on a
  running tokio runtime at export time.

## Open questions for review

1. **Cargo feature gate?** The exporter is always compiled but inert at runtime; it
   could move behind an off-by-default `otel` feature if the added compile deps are
   unwelcome by default. Happy to gate it either way.

## Testing

- `cargo +nightly-2026-04-14 fmt --check --all` — clean.
- `cargo +nightly-2026-04-14 clippy --locked --workspace --all-targets -- -D warnings`
  — clean (the CI bar).
- `cargo +nightly-2026-04-14 nextest run -p fabro-cli -E 'test(otel::)'` (or
  `cargo test -p fabro-cli --bin fabro otel::`) — green (both the `parse_protocol` and
  `resolve_endpoint` unit tests).
- Manual: with the endpoint env unset, tracing output is unchanged; with it set,
  spans export over OTLP/HTTP.
