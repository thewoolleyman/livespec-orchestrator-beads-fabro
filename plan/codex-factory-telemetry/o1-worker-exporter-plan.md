# O1 execution plan — activate the fabro OTLP exporter for the worker (bd-ib-98c.4)

**Execution-ready build plan for O1**, the first slice of the outward fabro emitter
spine. Grounded in fresh code verification on the `factory-integration` branch
(2026-07-16). Companion to `handoff.md` (the track overview) and `emitter-replan.md`
(the full O1–O5 decomposition).

## Not blocked — build on `factory-integration`

The transport (`bd-ib-i4r`, fabro#576) is already carried in `factory-integration`
(0.254 + `15b89ab`) and **pinned live** at `~/.fabro/bin/fabro`. O1 builds directly
on that branch; it does **not** wait on #576's upstream merge (that flip only starts
upstream acceptance). Base is settled at 0.254 (the `#474` ceiling). Drive O1
operator-side (Codex + Fable review loops), exactly like the transport was — it
becomes its own fabro PR.

## What is already true (verified on `factory-integration`, 2026-07-16)

- **The worker installs the OTLP layer.** `lib/crates/fabro-cli/src/logging.rs` wires
  `.with(otel::otel_layer())` at four tracing-config sites (`:368,:392,:419,:453`).
  The exporter is present; it is inert only because its env is absent.
- **The worker's env is cleared + narrowly allowlisted.** The fabro server spawns
  `fabro __run-worker` through `apply_worker_env` — `spawn_env.rs:6`
  `WORKER_ENV_ALLOWLIST` (FABRO_LOG / FABRO_HOME / FABRO_STORAGE_ROOT /
  FABRO_PUSH_CRED_REFRESH_*), `env_clear()` + narrow copy. **No `OTEL_*`.** So the
  worker never sees the exporter env.
- **The re-injection site exists and has an established pattern.**
  `worker_runtime.rs:89-98`: `apply_worker_env(&mut cmd)` (line 89), then explicit
  `cmd.env(EnvVars::FABRO_LOG, …)`, `FABRO_CONFIG`, `FABRO_WORKER_TOKEN`,
  `GITHUB_APP_PRIVATE_KEY` re-injections. O1's `OTEL_*` re-injection goes here,
  beside them.
- **The receiver is armed** at `172.17.0.1:4318` (docker bridge;
  `_otel_receive.py:63`, override `LIVESPEC_OTEL_RECEIVER_HOST`), json-only.
- **The Dispatcher already builds an OTEL overlay** — `_dispatcher_projection.py:39`
  (`DEFAULT_SANDBOX_OTEL_ENDPOINT = http://172.17.0.1:4318`), `:68-69`
  (`OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`),
  injected via `_dispatcher_credentials.py:153-164` (`otel_env=…`). **But this
  overlay targets the AGENT's telemetry inside the sandbox, not the fabro
  server/worker.** O1 wires the fabro processes; do not assume the agent overlay
  reaches them.

## Step 0 — confirm which process emits the target spans (do this FIRST)

The emitter's value depends on where the `run`/node/ACP spans originate. The handoff's
falsification established the ACP handler runs in the **server-spawned
`fabro __run-worker` subprocess** (production always takes the subprocess path). Before
writing code, confirm on a live `factory-integration` run:
1. Which process holds the span you want — the host fabro server (`127.0.0.1:32276`)
   or the `__run-worker` subprocess. Both create their own `info_span!("run", id)`.
2. Whether the host server needs `OTEL_*` at **start** (it is launched OAuth-only with
   no OTEL env today, so its own `run` span is also inert) in addition to the worker
   re-injection.

This gates whether O1 is worker-only or worker + server-start env.

## Step 1 — the code change (fabro Rust, on `factory-integration`)

At `worker_runtime.rs:89-98`, after `apply_worker_env`, re-inject the exporter env
from the server's environment into the worker `cmd`:
- `OTEL_EXPORTER_OTLP_ENDPOINT` (the receiver; `http://172.17.0.1:4318`)
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` — **mandatory**: the upstream exporter now
  defaults to `http/protobuf`, but our receiver is json-only, so protobuf POSTs are
  silently rejected.
- `OTEL_SERVICE_NAME` / the resource `service.name` (the receiver maps
  `service.name` → dataset; e.g. `fabro`).

**Do NOT** add `OTEL_*` to `WORKER_ENV_ALLOWLIST` — an allowlist copy would also sweep
`OTEL_EXPORTER_OTLP_HEADERS` (the Honeycomb API key) into the sandboxed worker. The
worker exports to the LOCAL receiver (no auth); the receiver adds Honeycomb egress
auth. Keep the key out of the worker. Explicit `cmd.env` of the three non-secret vars
only — mirror the `FABRO_LOG`/`FABRO_CONFIG` pattern.

If Step 0 shows the host server also needs it, set the three vars in the server's
launch env (an ops/runbook change in `orchestrator-image/README.md` §"Host Fabro
server", not a code change) — again endpoint + `http/json` + service.name, **no
HEADERS**.

## What O1 does NOT do (keep the slices honest)

- **No new spans.** O1 exports only the EXISTING single `run` span per process (the
  tracing tree is one span deep — `run/mod.rs:96` etc.). Node-lifecycle and ACP-turn
  spans are O3/O4 (`bd-ib-98c.6/.7`).
- **No cross-process trace join.** Server and worker each mint their own `run` span
  with no `traceparent`, so O1 yields two disconnected traces per dispatch. W3C
  `traceparent` injection/extraction at the same `worker_runtime.rs` seam is O2
  (`bd-ib-98c.5`) — the strict next slice.
- **No token/cost.** `acp.rs` hardcodes `usage: None`; that is O5 (`bd-ib-98c.8`,
  deferred).

## Verification (the gate before calling O1 done)

1. CI-equivalent on `factory-integration`: `fmt --check` + `clippy --locked
   --workspace --all-targets -- -D warnings` + tests under the pinned nightly.
2. Rebuild the host binary from `factory-integration` and re-pin (per
   `orchestrator-image/README.md`); rebuild the orchestrator image too (it bakes a
   COPY — else the containerized server runs the old fabro).
3. A proof-dispatch → confirm a fabro `run` span (worker and/or server) lands in the
   Honeycomb dataset its `service.name` maps to, with attributes intact. This is the
   real end-to-end proof deferred from the transport work.
4. Update `bd-ib-98c.4` + `handoff.md` with the result; then O2 (traceparent) is next.

## Review criteria (Codex + Fable loops, like the transport)

Completeness (nothing half-wired); narrow fix; low blast radius; loose coupling;
preserves all existing fabro APIs/patterns; **no regressions in fabro OR livespec**;
the Honeycomb key never reaches the worker.
