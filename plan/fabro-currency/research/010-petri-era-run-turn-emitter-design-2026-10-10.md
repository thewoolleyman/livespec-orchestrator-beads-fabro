# 010 — Petri-era run_turn emitter design (2026-10-10)

Work item bd-ib-6vhgqg, first deliverable: the emitter design the carry
must implement on the rebuilt carrier. Revisions cited: Fabro candidate tag
`v0.378.0-nightly.0` (commit 64b9d8815), Petri `e46845bd` (the revision
that tag locks), the 0.254 carrier `8869e88b2`, and this repository's
Dispatcher at `71d4e6a38`. Every path and line below was read at that
revision; nothing is inferred from the pre-Petri layout.

## What the contract needs

contracts.md, Built-in ACP node defaults: a reader can check the rendered
adapter string's clear command and args plus the digest of the complete
rendered bytes against the redacted `run_turn.command` record the factory
emits, and raw environment values never ride that trace. The Dispatcher's
consumers key on four correlation attributes (`_otel_enrich.py:102-105`):
`work.item.id`, `livespec.dispatch.id`, `fabro.run_id`,
`livespec.dispatch.factory`. The receiver accepts `/v1/traces` and
`/v1/metrics` only (`_otel_receive.py:78-79`). Plan
factory-run-correlation-observability requires the factory attribute and
the W3C traceparent join to survive.

## What exists on each side

- 0.254 carrier: `lib/crates/fabro-workflow/src/handler/llm/acp.rs:849`
  builds `command_display = process_spec.to_string()` and `:1055` opens
  `tracing::info_span!("run_turn", command = %command_display, ...)`.
  No digest is computed anywhere on the ACP path. The span is closed by the
  handler when the turn ends. The code it lives in was replaced by Petri.
- Candidate tag: zero OTLP or OpenTelemetry code; worker tracing is
  initialised in `lib/apps/fabro-cli/src/logging.rs:45` (`init_tracing`,
  `EnvFilter` from `FABRO_LOG`); worker environment is assembled in
  `lib/apps/fabro-server/src/spawn_env.rs` (`apply_worker_env`).
- Petri: the agent launch is `crates/attractor/steps/src/agent/backend.rs`
  lines 95-149: `config.command()`, `command.spec(ctx.secrets)` resolves
  named secret references into a `ProcessSpec`, `Client::spawn(ctx.env,
  spec, ctx.logs, stage)` (`crates/attractor/steps/src/acp/mod.rs:177`)
  starts the agent in the acquired environment, then `open_session`. One
  prompt turn per node attempt, with the node `timeout` as the deadline;
  a failed turn maps to `retry_requested` and the engine re-fires a new
  attempt (`backend.rs:58-80`). The stage record carries `acp.turns`,
  `acp.usage` and `acp.context` (`acp/mod.rs:239-252`). Petri emits NO
  tracing spans on the agent or ACP paths.
- Petri seams a host may attach to: the environment trait `ExecEnv`
  (`crates/core/executor/src/env.rs:292`) whose `spawn(&self, spec:
  ProcessSpec)` (`:293`) is the single process-launch surface, and whose
  `ProcessSpec` (`env.rs:26`) carries `program`, `args`, `env`, `cwd`,
  `stdin`, `output`, `timeout`; the `Executor` trait
  (`crates/core/executor/src/scope.rs:380` `acquire`, `:388` `release`);
  and `ExecutionHooks` (`crates/core/driver/src/lifecycle.rs`:
  `before_attempt`, `prepare_result`, `after_record`, `transition`,
  `run_finished`, `scope_released`, `scope_acquired`).
- Fabro already uses both seams: `CredentialExecutor`
  (`lib/components/fabro-petri/src/stage_credentials.rs:133`) wraps
  `acquire` and returns the acquired environment inside its own `ExecEnv`
  implementation (`Arc::new(env)` at `:134-150`); `FabroHooks`
  (`lib/components/fabro-petri/src/hooks.rs:1511`) implements every
  `ExecutionHooks` method, with `after_record` currently delegating.

## Decision: a Fabro-only emitter, no Petri change

A `TelemetryExecutor` layered exactly like `CredentialExecutor` (installed
through `runtime.executor_layer` at `engine.rs:232`) wraps the acquired
environment and observes every `spawn(ProcessSpec)`. That is where the
complete rendered command exists on the Petri side of the boundary, after
secret resolution and before the process starts, so the digest is taken
over what actually launched, never reconstructed from the graph. Turn
boundaries come from `FabroHooks`: `before_attempt` opens the attempt,
`after_record` sees the stage record with `acp.turns`, `acp.usage`,
`acp.context` and the outcome, and closes it. No Petri extension is
required for this; the upstream contribution is the OTLP transport (PR
576's successor), not an engine hook.

### Span model

- `run_turn` (name kept for consumer compatibility): one span per ACP node
  attempt, keyed by `(execution, firing, attempt)` from the hook context.
  Opened at `before_attempt` for a node whose kind is agent, closed at the
  record for that attempt. Status: ok on `end_turn`, error on any
  `AcpError` (the message carries the stop reason), cancelled on
  `AcpError::Cancelled`.
- Attributes: `fabro.run_id`, `fabro.node`, `fabro.firing`,
  `fabro.attempt`, `run_turn.command` (shell-quoted program and args, as
  today), `run_turn.command.digest` (below), `run_turn.env.keys` (sorted
  key names only), `acp.turns`, `acp.usage.*`, `acp.context.*` from the
  record, `acp.stop_reason`.
- Correlation: `work.item.id`, `livespec.dispatch.id`,
  `livespec.dispatch.factory` arrive as OTLP resource attributes set from
  the worker environment (`OTEL_RESOURCE_ATTRIBUTES`, re-injected by the
  worker env carry at `spawn_env.rs`), so every span the worker emits
  carries them without the emitter knowing the Dispatcher's names.
- Parentage: the worker's root span is created under the `traceparent`
  the Dispatcher placed in the worker environment (the O2 carry), and the
  `run_turn` span is a child of the attempt's span, so the Dispatcher's
  dispatch span is an ancestor.

### Digest

`sha256` over a canonical encoding of the launched `ProcessSpec`: the
program, each arg in order, and for the environment each sorted key
followed by `sha256(value)`; values never enter the digest input directly
and never appear on the span. Changing one environment value changes the
digest while no record exposes the value, which is the discriminating test
the item's Definition of Done names. The Dispatcher computes the same
digest from its own rendering of the adapter string and the overlay it
wrote, so the comparison the contract asks for is digest to digest.

### Transport

The OTLP/HTTP span exporter from PR 576 is re-attached in
`lib/apps/fabro-cli/src/logging.rs::init_tracing` behind the standard
`OTEL_EXPORTER_OTLP_*` variables, with the fork-local P2 rule retained:
export is independent of `FABRO_LOG`. Encoding `http/json` on
`/v1/traces` to match the receiver. Workers receive the exporter variables
through `apply_worker_env`; the credential-bearing header stripping the
runbook documents stays.

## Dispatcher changes carried by the same item

- `_dispatcher_run_turn_guard.py::_observable_from_dispatch_record` reads
  the receiver's reachability for the dispatch's factory instead of the
  literal name `hp`.
- `_dispatcher_run_turn_sink.py` attributes an export to a dispatch by the
  correlation ids and no longer counts the global `fabro.run_turn`
  last-export key as a per-dispatch hit.
- `_otel_enrich.py` joins run identity from the `fabro.run_id` attribute
  on every span rather than from the legacy event names
  `Workflow run started` and `Sandbox initialized`, which Petri-era runs
  do not emit.

## Proof plan (the item's host-captured assertions)

One dispatch routed to the hp candidate instance; its `run_turn` record in
Honeycomb's `fabro` dataset carries the four correlation attributes, the
command and the digest, and no environment value; a second dispatch with
one changed environment value produces a different digest; a concurrent
legacy-instance run does not satisfy the candidate dispatch's query; with
the candidate exporter disabled the query returns nothing while legacy
telemetry continues; the record's parent chain reaches the Dispatcher's
dispatch span.

## Open items

- Whether `EnvHandle` exposes enough of the scope (node name, firing,
  attempt) at `acquire` time for the wrapper to tag spawns, or whether
  the hook context must hand the executor a per-attempt token. Read
  `scope.rs::AcquireContext` during implementation.
- `after_record` fires after the record is durable; a span closed there
  carries the record's timestamps, not the process exit; the process
  exit time is available from the wrapped `ProcessHandle` and is the
  better end time.
