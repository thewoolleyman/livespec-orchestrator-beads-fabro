# Dossier 007 — CORRECTION to 005: a remote fail-fast IS feasible; the heartbeat liveness channel exists, is wired, and is DARK

Correction note for plan thread `acp-implement-zero-output-hang` (epic
`bd-ib-b5dg`), compiled 2026-09-04. It **retracts the headline conclusion of
research/005** ("a remote-signal fail-fast is INFEASIBLE"). 005's measurements of
the fabro EVENT stream are valid, but its conclusion was reached by an instrument
aimed at the wrong channel: it never considered the metrics-HEARTBEAT liveness
channel that this repo already built and wired for exactly this purpose. Labels
**measured** / **inferred** as before.

## Why 005 was wrong

005 measured the fabro event stream and `fabro ps` `status_kind`, found both blind
inside an ACP turn, and concluded no remote signal can distinguish a healthy-but-
event-frozen turn from a zero-output hang below the ceiling. That is true **of
those two channels**. But the orchestrator's stall watchdog does not rely on them
as its primary signal. The landed design (work-items `livespec-impl-beads-29f.6`
and `29f.7`, both closed) adds a THIRD channel:

- `_dispatcher_heartbeat_probe.py` — `HeartbeatLivenessProbe` reads CC's metrics
  heartbeat, which "exports on a SHORT interval and keeps advancing while an agent
  turn is genuinely alive" (its own docstring). `LayeredLivenessProbe` composes it
  as the deferred-PRIMARY with the coarse `fabro events` wall-clock probe as the
  PERMANENT fallback, both feeding the same `decide_stall`.
- It IS wired into the current dispatch path: `_dispatcher_io_fabro_launcher.py`
  (`_sample`, lines ~233-240) builds the `LayeredLivenessProbe` when
  `heartbeat_path` is set, and `_dispatcher_loop_run.py:84` sets `heartbeat_path`
  on the standard loop dispatch. This is the same launcher Child A (PR #2036)
  reworked.

CC's metrics heartbeat is exported OUT OF BAND from the ACP session/update
notifications that `fabro-acp/src/session.rs` drops. So the event-bridge blindness
dossier 001/005 documented does NOT apply to it. A healthy-but-event-frozen turn
(the 2026-09-02 specimen `01M1HEAW`) is still emitting metrics heartbeats while its
fabro event stream is silent — which is exactly the discriminator 005 declared did
not exist.

## Measured — the heartbeat pipeline is DARK fleet-wide

The channel exists and was live, but is not flowing now. The receiver writes a
`<journal>-otel-heartbeat.json` sink (a scrubbed `key -> last-beat-epoch` map).
Newest beat in every tenant's heartbeat sink on this host (2026-09-04):

| tenant | newest heartbeat beat |
|--------|----------------------|
| livespec-orchestrator-beads-fabro | 2026-08-30T17:08Z |
| livespec-overseer | 2026-08-22T10:18Z |
| livespec-console-beads-fabro | 2026-08-22T02:20Z |
| livespec-dev-tooling | 2026-08-17T13:53Z |
| (all others) | 2026-08-09 … 2026-08-17 |

Nothing anywhere has beaten since **2026-08-30**. Yet dispatches are running
normally in September, and the OTLP receiver IS up: the TRACE/span sinks
(`-calibration-spans.jsonl`, `-reflection-spans.jsonl`, `-cost-report-spans.jsonl`)
are being written on 2026-09-02 and 2026-09-04. It is specifically the
METRICS-derived sinks that stopped: the `-otel-heartbeat.json` AND the
`-otel-cost.json` sinks both froze at the same ~08-22–08-30 boundary while the span
sinks kept flowing. So the OTLP **metrics** pipeline regressed fleet-wide; the
traces pipeline is unaffected.

The 2026-09-02 healthy specimen `01M1HEAW` (console) has NO beat in the console
heartbeat sink — consistent with the metrics pipeline already being dark for
console since 08-22.

## Inferred — this explains the whole puzzle

With the heartbeat PRIMARY dark, `LayeredLivenessProbe` gets "no signal" from the
primary on every sample and falls through to the coarse wall-clock/event-stream
FALLBACK. That fallback cannot safely fire below the ceiling — because, per
research/005, healthy runs are event-frozen for a median of 28 minutes, so a
fallback that fired on event-staleness would false-kill the majority of healthy
work. So the watchdog correctly does nothing, and the hang sails to its ceiling.
This is why research/004 found "zero stall-cancels ever on hp": not because the
signal is fundamentally indistinguishable (005's claim), but because the channel
that WOULD distinguish it has been dark since before the measurement window.

## Corrected direction for Child B (`bd-ib-q5wxkh`)

Supersedes research/005's recommendation (D3 fabro-side event-bridge fix / accept
infeasibility). The remote fail-fast is FEASIBLE and largely built. Child B's real
deliverable is:

1. **Restore the metrics-heartbeat pipeline.** Diagnose why the OTLP metrics path
   went dark ~08-22–08-30 while traces kept flowing — CC's in-sandbox metrics
   export vs the receiver's metrics→HeartbeatSink routing. (One more probe pins
   which side; not done here.)
2. **Verify the discriminator empirically:** confirm a healthy-but-event-frozen
   turn keeps beating (so it is NOT killed) while a genuine zero-activity hang does
   not (so it IS caught) — best measured on a fresh live specimen with the pipeline
   restored.
3. **Design the hung-vs-outage discriminator.** A genuine hang produces NO beat for
   its run key; so does a pipeline outage. The current probe fail-SAFELY treats "no
   signal" as "do not kill" (correct — a metrics outage must never be read as a
   stall). To fail-fast a hang, distinguish the two: e.g. the pipeline is provably
   healthy (other concurrent runs' keys ARE beating) while THIS run's key never
   beats within a bounded first-beat deadline after `agent.session.activated`. This
   dovetails with dossier 006's finding that 14/15 hangs strike the FIRST ACP turn
   (implement, visit 1): the signature is "first activation, no first beat, pipeline
   otherwise healthy."

The fabro-side event-bridge fix (D3) is NOT required for this path.

## New finding worth its own tracking

The metrics regression is not just a hang-watchdog problem: the SAME cutoff froze
the `-otel-cost.json` cost sink, so the Dispatcher's per-dispatch cost gate has been
reading a stale/empty cost signal fleet-wide since ~08-22–08-30. No ledger item
tracks this regression (prior-art scan 2026-09-04 found only the closed 29f.*
builders; `bd-ib-dbzp` "Codex spend telemetry never reaches the destination" is
possibly related but Codex-spend-specific). This warrants its own defect item; it
is broader than this plan.

## Honesty caveats

- Exact root cause of the metrics regression (CC export side vs receiver routing
  side) is not pinned here — one more probe (inspect a live dispatch's OTLP metrics
  traffic vs the receiver's metric handling) settles it; that is Child B's leg 1.
- A standalone `heartbeat_lookup_keys` call returned RAW ids while the sink keys are
  hashes; that per-run lookup was therefore inconclusive on key form (likely a
  scrubber-config difference between the standalone call and the live dispatch). The
  fleet-wide DATE gap (no beats after 08-30) is decisive independent of key form and
  is what this correction rests on.
- research/005's event-stream measurements stand; only its "infeasible" CONCLUSION
  is retracted.
