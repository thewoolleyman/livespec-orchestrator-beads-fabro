# Dossier 008 — ROOT CAUSE: the heartbeat liveness probe is keyed WRONG; it can never match, so the primary signal is a no-op

Root-cause note for plan thread `acp-implement-zero-output-hang` (epic
`bd-ib-b5dg`), compiled 2026-09-04, following research/007. 007 established that
the metrics-heartbeat channel exists, is wired, and is currently dark. This note
finds a SECOND, more fundamental defect that is independent of the dark pipeline:
even when beats flow, the watchdog's heartbeat probe **cannot read them**, because
the sink and the probe key beats on DIFFERENT ids. Empirically verified. Labels
**measured** / **inferred**.

## The mechanism

- The dispatcher projects CC's in-sandbox OTel resource attributes via
  `cc_otel_overlay_env` (`_dispatcher_projection.py`): it emits
  `work.item.id=<id>` and `livespec.dispatch.id=<id>` — but NOT `fabro.run_id`
  (the run id is not known at projection time).
- The receiver keys each beat by `_preferred_key` (`_otel_parse.py`), whose
  preference order is `fabro.run_id` > `livespec.dispatch.id` > `work.item.id` >
  `session.id`. Since `fabro.run_id` is absent and `livespec.dispatch.id` is
  present, **every beat is keyed by `livespec.dispatch.id`.**
- The watchdog probe builds its lookup keys with
  `heartbeat_lookup_keys(work_item_id, run_id)`
  (`_dispatcher_heartbeat_probe.py`) — it looks up ONLY the scrubbed `run_id` and
  `work_item_id`. **It never looks up `livespec.dispatch.id`.**

So the probe's candidate keys (`run_id`, `work_item_id`) can never match the
sink's actual keys (`livespec.dispatch.id`). `HeartbeatLivenessProbe` therefore
always returns "no signal", and `LayeredLivenessProbe` always falls through to the
coarse wall-clock/event-stream fallback — which cannot safely fire (research/005:
it would false-kill the healthy event-frozen runs). The net effect: the finer
primary liveness signal the whole 29f.6/29f.7 design was built to provide has
never been readable by the watchdog.

## Measured — empirical proof

Cross-checked the 12 keys in the console heartbeat sink
(`livespec-console-beads-fabro/tmp/fabro-dispatch-journal-otel-heartbeat.json`)
against the id fields in that tenant's dispatch journal (2026-09-04):

- **6 of 12 heartbeat keys exactly match `dispatch_id` values** from the journal
  (e.g. `222ff47c2e06412fbc789c11ceb13063`, `0fa690060c3a457a90c300b6e801330b`,
  `bbec1ee9ae3842a79885600c7eb65da3`). The remaining 6 are the same 32-hex
  dispatch-id shape (older dispatches rotated out of the current journal).
- **0 of 141 `work_item_id` values match** any heartbeat key.
- **0 of 147 `run_id` values match** any heartbeat key.

Run ids are ULIDs (`01M0GF7333…`); dispatch ids are 32-hex
(`ba06d4268df24488a01beb352a6d0e7f`); the heartbeat keys are 32-hex and coincide
with dispatch ids. `scrub` does not hash (it only redacts credential-URLs and
truncates), so these keys are the raw ids, confirming the identification.

## Why this is the deeper root cause

research/004 measured "zero stall-cancels EVER on hp" and left the reason as a
hung-state-specific discovery hypothesis. This defect explains it directly and
more completely: the watchdog's primary liveness probe has been structurally
unable to match a single beat for the entire life of the feature, on every run,
hung or healthy — not merely since the pipeline went dark. The dark-pipeline
regression (007) is real and additional, but even fully restored it would change
nothing until this keying is fixed.

It also means research/005's "healthy and hung are indistinguishable" is doubly
not-fundamental: the distinguishing signal (the beat) not only exists and is
out-of-band from the event bridge, it was being RECORDED under the dispatch id —
just never looked up.

## Corrected Child B (`bd-ib-q5wxkh`) deliverable — now small and concrete

This turns Child B from "restore a pipeline / design a discriminator" (007) into a
tight, well-defined keying fix, plus the restore:

1. **Align the heartbeat key between sink and probe (the core fix).** Options:
   - Have the probe ALSO look up `livespec.dispatch.id` — the dispatcher mints the
     dispatch id and can thread it into the watched-launcher probe construction
     (it already threads `work_item_id` and discovers `run_id`). This matches the
     sink's current highest-available key. Preferred: minimal, and dispatch id is
     the most specific stable id both sides can share.
   - OR change the sink preference so `work.item.id` outranks
     `livespec.dispatch.id` (both are projected; the probe already looks up
     `work_item_id`). Simpler on paper, but `work.item.id` is not unique across
     re-dispatches of the same item, so a stale beat from a prior dispatch could
     be read as current — the dispatch id avoids that. Weigh this trade-off.
   - Emitting `fabro.run_id` into the resource attrs is NOT available — the run id
     does not exist at projection time.
2. **Restore the metrics pipeline (research/007).** Independently, beats stopped
   fleet-wide ~08-30; the keying fix is inert until beats flow again.
3. **Verify end to end** on a live specimen once (1)+(2) land: a healthy-but-
   event-frozen turn keeps beating (not killed) while a genuine zero-activity hang
   produces no beat under its dispatch key (caught). Still design the hung-vs-
   outage discriminator (research/007) so a pipeline outage is not read as a hang.

The fabro-side event-bridge fix (D3) remains unnecessary.

## Honesty notes

- The keying defect and the dark-pipeline regression are SEPARATE; this note does
  not conflate them. Both must be fixed for the fail-fast to work; neither alone
  suffices.
- The 6/12 match is on the live console journal; the other 6 keys are consistent
  in shape (32-hex dispatch ids) but predate the journal's current window, so they
  are inferred, not matched. The 6 confirmed matches plus 0/141 work-item and
  0/147 run-id matches are already decisive for the direction of the mismatch.
- Not verified here: that a genuine hang produces NO beat under its dispatch key
  (leg 3 above) — that needs a live specimen with the pipeline restored and the
  keying fixed. The defect proven here is upstream of that and blocks it.
