# Dossier 009 — the heartbeat is a PROCESS-LIVENESS ping, not a TURN-PROGRESS signal; fixing the key (008) is necessary but not sufficient

Qualification note for plan thread `acp-implement-zero-output-hang` (epic
`bd-ib-b5dg`), 2026-09-04. It tempers research/008's "small concrete keying fix"
framing: aligning the heartbeat key is genuinely required, but by itself it will
NOT make the fail-fast work, because of what the heartbeat actually measures.
Labels **measured** / **inferred**.

## Measured — what the heartbeat actually is

- The sandbox OTel overlay sets `OTEL_METRIC_EXPORT_INTERVAL=10000`
  (`_dispatcher_projection.py`): CC exports metrics every **10 seconds**.
- The receiver's `_handle_metrics` (`_otel_receive.py`) records
  `heartbeat.beat(key=..., at=now)` for **every metrics REQUEST it receives**,
  independent of whether any metric VALUE changed.

So a "beat" means "CC sent a metrics export in the last interval" = the CC process
is alive and its OTel exporter timer is firing. It does NOT mean the agent made
inference or tool progress.

## Inferred — why this breaks the discriminator, keying aside

The zero-activity hang keeps the CC PROCESS ALIVE: the 2026-09-02 in-sandbox
capture of a specimen-shaped run showed `npx claude-agent-acp` → `claude` alive,
`State S`, `wchan=ep_poll` (blocked in the event loop, not dead). A live process
with a running OTel SDK will keep firing its 10-second periodic metric export.
Therefore, once the key is fixed (008), the probe would most likely see the
heartbeat STILL BEATING during a zero-activity hang — and `decide_stall` would
read that as liveness and decline to kill. The heartbeat distinguishes
"process dead / exporter down" from "process alive"; it does not distinguish
"hung" from "productive". That is the wrong axis for this defect.

This means the feasibility arc across 005-008 lands at a more guarded place than
008 implied:

- 005 said infeasible — wrong reason (only examined the blind event stream).
- 007 said feasible via the heartbeat channel — right that the channel exists and
  is out-of-band, but too optimistic about what it measures.
- 008 found the key mismatch — a real bug, but fixing it is necessary, not
  sufficient.
- 009 (here): the heartbeat as currently defined is a liveness ping, not a
  progress signal, so it cannot by itself discriminate a zero-activity hang.

## The signal the fail-fast actually needs

A signal whose VALUE advances only on agent ACTIVITY, sampled for advancement
(not mere arrival):

1. **A progress metric, tracked by value.** CC emits event-driven counters
   (`claude_code.token.usage`, `claude_code.cost.usage`,
   `claude_code.lines_of_code.count`, …) that increment only on API calls / tool
   work. A watchdog that records the latest VALUE of such a counter per run key
   and stalls when the value has not advanced for N seconds WOULD discriminate: a
   zero-activity hang makes no API calls, so the counter is flat, while its export
   requests keep arriving. This is a change to what the sink stores (value, not
   just arrival time) and to `decide_stall` (advancement, not freshness) — larger
   than the 008 keying fix, but still orchestrator/receiver-side.
2. **OR the fabro-side per-turn signal (D3).** A fabro-emitted per-turn liveness /
   restored ACP `ToolCall` notifications would give turn-granular progress
   directly. Heavier (upstream/fork fabro), and 007 preferred to avoid it — but if
   CC exposes no value-advancing metric usable this way, D3 becomes the path.

## Corrected Child B (`bd-ib-q5wxkh`) deliverable

Supersedes 008's "small keying fix" as the WHOLE story:

1. Fix the sink/probe key mismatch (008) — still required for any heartbeat use.
2. Restore the metrics pipeline (007) — still required; beats have not flowed
   since ~08-30.
3. **Change the liveness signal from arrival-based to progress-based** — track a
   value-advancing CC activity counter, or adopt the fabro-side per-turn signal.
   This is the crux the earlier notes under-weighted.
4. Verify on a live specimen: confirm the chosen progress metric is flat during a
   genuine zero-activity hang while advancing on a healthy turn.

## Honest open question (the crux, needs a live specimen)

Whether CC keeps EXPORTING metrics during a zero-activity hang — and if so which
counters stay flat vs advance — is not settled from historical data (the console
journal rotated, so old hang specimens could not be mapped to their dispatch keys;
and the pipeline is dark now). The 10-second export interval plus the
process-alive capture make "the heartbeat keeps beating during a hang" the strong
expectation, but the decisive confirmation is a live specimen caught with the
pipeline restored and per-metric values observed. Until then, do NOT assume the
heartbeat (even keyed correctly) discriminates the hang.
