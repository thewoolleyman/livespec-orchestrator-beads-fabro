# 011 — Simulated hang: CC's metric-emission model resolves Child B without a wild specimen

Date: 2026-09-08. Author session: acp-implement-zero-output-hang (resume).
Supersedes the "wait for a live in-sandbox specimen" gate that Child B
(`bd-ib-q5wxkh`) and Child D (`bd-ib-y3vnpi`) carried. The specimen's only job
was to answer one empirical question about the watchdog's liveness signal; that
question is answered here by a controlled local simulation plus hermetic
verification against the real code, so the intermittent-hang lottery is no
longer on the plan's critical path.

## What was measured (not argued)

Claude Code **2.1.263** (the same build the factory sandbox runs) driven headless
(`claude -p ... --dangerously-skip-permissions`) with this repo's EXACT sandbox
OTel overlay env (`cc_otel_overlay_env`: `CLAUDE_CODE_ENABLE_TELEMETRY=1`,
`OTEL_METRICS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`,
`livespec.dispatch.id` resource attr, `OTEL_METRIC_EXPORT_INTERVAL` 5–10 s),
exporting to a local OTLP/HTTP-JSON capture server that logs every `/v1/metrics`
POST's arrival time and summed `claude_code.token.usage`.

Trap avoided: the operator's `~/.claude/settings.json` `env` block force-sets
`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` + `grpc` and OVERRIDES process
env, so the first runs sent gRPC elsewhere and captured nothing. A `--settings`
override file restored the http/json endpoint. In the real sandbox there is no
such user settings file, so the overlay env wins natively.

Four runs:

| run | condition | wall | metric beats | pattern |
|-----|-----------|------|--------------|---------|
| idle-sleep | 75 s foreground `sleep` (no inference) | 83 s | **2** | beats at +6.7 s and +82.8 s; **none during the 75 s idle** |
| long-inference | one 122 s streaming essay (28 k tokens) | 133 s | **2** | beat at +0 s and +122.7 s; **none during the 122 s single call** |
| tool-loop | 6 separate Bash tool calls | 21 s | **4** | beats at +0/+5/+10/+12 s, `token.usage` rising each time |
| fifo-block | CC blocked ~43 s on `cat fifo` (free event loop, no tokens) | 48 s+ | **2** | beats at +0 s and +5 s (the call that decided to run `cat`); **none during the 43 s free-loop idle** |

## The model this establishes

**CC emits a `token.usage` metric beat only when `token.usage` actually advances
— i.e. when an API call completes having consumed tokens. It does NOT emit
flat-value heartbeats on the configured export interval during a no-token window,
whether the event loop is blocked (sleep) or free (fifo-block).** Empty exports
are skipped. During active tool-loop work, beats arrive ~every 5 s with rising
`token.usage`; during any single long call or any idle stretch, they go dark.

This CORRECTS the load-bearing premise in `_dispatcher_heartbeat_probe.py`'s
docstring ("CC's metrics heartbeat exports on a SHORT interval and keeps
advancing while an agent turn is genuinely alive"). It does not keep advancing
during a single long operation or an idle window.

## Consequence for the watchdog (the whole point)

The sink stores `{key -> last-beat epoch}` and `decide_stall` treats an advancing
beat as progress. Given the emission model:

- **A zero-output hang** (`active_time_ms=0, inference_time_ms=0`, no API call
  ever) consumes no tokens → **emits no beats** → the sink's last-beat for that
  dispatch flatlines → `decide_stall` returns **STALLED** once the silent span
  reaches `stall_seconds` (default 1500 s = 25 min), **below fabro's 30-min ACP
  turn ceiling**. This is Scenario X; the landed fixes already cover it.
- **Slice 2 (switch the signal to `token.usage` VALUE-advancement) is
  REDUNDANT.** Because CC only beats when `token.usage` advances, "a beat
  arrived" already ⟺ "progress was made". Value-advancement and arrival are the
  same event; there is no alive-but-beating-flat hang for a value signal to catch
  that arrival misses.

### Hermetic verification against the real code

`decide_stall` and `HeartbeatLivenessProbe` are pure over an injected sink +
clock. Driving the REAL classes:

- flat heartbeat across a span > `stall_seconds` → **STALLED**; advancing → CONTINUE.
- real `HeartbeatLivenessProbe` over a synthetic sink where a dispatch beats once
  then goes silent for 26 min → **STALLED** (fires at 25 min < 30-min ceiling).
- a newer beat arriving (progress) → **CONTINUE** (no false kill).

### Production confirmation (research/010 + this pass)

The vps dispatcher-local sink `tmp/fabro-dispatch-journal-otel-heartbeat.json`
was frozen 2026-08-30 → 09-06 and resumed on release day (9 beats 09-06, 29 on
09-07), keyed by `dispatch_id` and mapping to `factory=hp` — the restored
cross-host loop, live in production.

## Residual risk (stated, not hidden)

A HEALTHY turn stuck in ONE single API call longer than `stall_seconds` with no
tool use would also go beatless and be false-killed. Real `implement` turns are
tool-loop-heavy (each call beats within seconds), so the CC-metrics-arrival
signal is far finer than the fabro event stream research/005 measured (whose
p50=28 min silence is the `activated -> deactivated` bridge gap, NOT the
per-API-call metric beat). The exposure is confined to atypical single-long-call
turns; the wall-clock `fabro events` fallback in `LayeredLivenessProbe` remains
the backstop. This is a tuning question, not a blocker, and is the only part of
the design a real specimen could still refine.

## Boundary

The simulation reproduces "CC alive, no token consumption" — the defining trait
of the zero-output hang (`inference_time_ms=0`). Whatever the hang's exact
internal wedge, it consumes no tokens, so it emits no beats, so it is caught. The
one thing simulation cannot pin is the hang's ROOT CAUSE (launch-env/token
hypothesis, Child D) — but with the watchdog now firing below the ceiling, the
2×30-min burn is prevented regardless of root cause, which was the epic's aim 2.
