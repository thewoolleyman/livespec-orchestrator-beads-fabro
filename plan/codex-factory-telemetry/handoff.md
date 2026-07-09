# Handoff — codex-factory-telemetry

## What this thread is

Restore end-to-end factory observability for the **Codex era**. The
Honeycomb telemetry pipeline is Claude-Code-native and has been dark for
every run since ~2026-06-13 because the factory now drives work with
Codex (`@zed-industries/codex-acp@0.16.0`), which emits none of the
telemetry the pipeline captures. The receive/egress plane is intact and
armed on every dispatch; the gap is purely the **emitter**.

## Read-first chain (open these, in order, before acting)

1. `plan/codex-factory-telemetry/research/observability-gap.md` — the
   full reasoning: the evidence (dataset dark-dates), the mechanism (why
   Codex emits nothing), what is already intact and reusable, the three
   approach options, and the open questions. **This is the load-bearing
   context; do not proceed without it.**
2. `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_plan.py`
   — `cc_otel_overlay_env()` (the CC-only overlay),
   `DEFAULT_SANDBOX_OTEL_ENDPOINT` (`http://172.17.0.1:4318`),
   `CODEX_IMPLEMENTER_ADAPTER` (the Codex adapter pin).
3. `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_receive.py`
   — the host OTLP receiver (port 4318, JSON-only today).

## Next action (exactly one)

**Investigate whether `@zed-industries/codex-acp@0.16.0` (and the
`codex-core` it wraps) can emit OpenTelemetry** — read-only. Determine:
does it honor any standard `OTEL_*` env var, or expose any telemetry/
event-export hook? Capture the answer as a new research note
(`plan/codex-factory-telemetry/research/codex-otel-support.md`). That
answer selects the approach:

- **If Codex honors `OTEL_*`** → Approach 1: it may already be one
  `service.name` + a receiver-protocol check away (the sandbox already
  has `OTEL_EXPORTER_OTLP_ENDPOINT` set at container level). Confirm the
  29f receiver (`_otel_receive.py`, JSON-only) accepts Codex's protocol,
  or teach it `http/protobuf`.
- **If not** → Approach 2: emit the agent/orchestration layer from
  fabro's ACP handler via the fabro-side OTLP exporter being added on
  the `fabro-token-refresh` track (coordinate with it), and decide
  whether a wrapper around the adapter command is also needed.

Then file the chosen build steps as ready ledger work (see below).

## Ledger status

**DEFERRED epic-anchor.** The ledger is healthy (dolt on
`127.0.0.1:3307`), but this thread was authored from an **unwrapped**
session (no `BEADS_DOLT_PASSWORD`), and the plan operation requires the
epic anchor to route through the `capture-work-item` **consent seam**
(never a raw `bd` write) — which needs the env wrapper. So the anchor is
left for the properly-wrapped driving session. Per the plan operation a
thread should anchor an `epic`-type work-item as its status anchor. The
driving session MUST, as its first ledger-touching act (running under
`/data/projects/1password-env-wrapper/with-livespec-env.sh --`):

1. File the epic anchor via the `capture-work-item` operation — an
   `epic` titled "Codex-era factory telemetry" — and record its id here.
2. Route ripe build steps as CHILD work-items (`depends_on` the epic)
   via `capture-work-item`; never hand-code them inline (factory-side
   build under the janitor gate).

Until then, status is composed from this file, not the ledger.

## Coordination

Coordinate with the **`fabro-token-refresh`** plan thread: it is adding
OTLP export to fabro (upstream-worthy) to debug the >60-min expired-
token bug. Agree on receiver protocol (json vs protobuf), dataset/
`service.name` naming, and correlation attributes so both emitters land
coherently.

## Do NOT

- Do not implement inline in a planning session — FILE ripe work to the
  ledger; the Dispatcher / `drive` builds it factory-side.
- Do not let any emitter ship unredacted prompts / tool I/O / raw API
  bodies out of the sandbox (mirror the CC content-flags-off hygiene).
