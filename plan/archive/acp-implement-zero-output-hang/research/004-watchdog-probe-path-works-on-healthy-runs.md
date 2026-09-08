# Dossier 004 — the watchdog probe path WORKS on healthy runs; research 003's discovery-blindness cause is downgraded

Root-cause correction for plan thread `acp-implement-zero-output-hang`
(epic `bd-ib-b5dg`), compiled 2026-08-30 after Children A (PR #2036, observability)
and C (PR #2038, telemetry) merged. Live measurements against hp plus the hung-run
dump. Labels **measured** / **inferred** / **hypothesis** as before. This dossier
CORRECTS the confidence of dossier 003 — read them together.

## Why this pass happened

Dossier 003 concluded the leading cause was `_discover_run` blindness — that
`fabro ps -a --json --server hp` omits the in-flight run, so the watchdog's
per-poll discovery silently `continue`s and `decide_stall` is never consulted. It
explicitly hedged that the exact sub-condition needed a LIVE-run measurement. This
pass took that measurement — and it refutes the blanket form of the hypothesis.

## Measured

1. **A healthy in-flight run IS fully discoverable on hp.** Live run
   `01M196Y7D9M7KP6FFG9KSP6DHS` (`overseer-nwtw`), status `running`:
   - `fabro ps -a --json --server hp` LISTS it, `status_kind=running`, and the
     `^Work-item:` regex extracts `overseer-nwtw` from its ps `goal` (goal_len 8697).
   - `fabro events <id> --json --server hp` returns 74 events, every one carrying a
     `ts` field (last ts advancing), keys `[actor, event, id, properties, run_id, ts]`.
   So ps-discovery, the events probe, and (below) timestamp parsing all WORK for a
   healthy in-flight run. The BLANKET "ps omits all in-flight runs" form of 003 is
   refuted.

2. **The watchdog parses the live `ts` key.** `_event_epoch`
   (`_dispatcher_watchdog.py`) reads `("timestamp", "ts", "at")`, so the live
   stream's `ts` is handled. The dump's `events.jsonl` used `timestamp`/`type`; the
   live `fabro events --json` uses `ts`/`event` — a schema difference that does NOT
   defeat the probe. Key-mismatch hypothesis: refuted.

3. **The stall floor is correct and below fabro's turn timeout.**
   `DEFAULT_STALL_SECONDS=1500` (25 min); `LIVESPEC_DISPATCH_STALL_SECONDS` is unset
   in the dispatch env and overridden nowhere (`.livespec.jsonc`, workflow, overlay).
   1500 < fabro's 1800s (30-min) ACP turn timeout, so the watchdog SHOULD pre-empt.

4. **The hung run's event stream WAS truly frozen.** In run
   `01M17P0QHRH7ZYXJ6DVTRSFAV4`'s first hung turn, the ONLY events between
   `agent.session.activated` (21:15:34Z) and `agent.acp.timed_out` (21:45:34Z) are
   the endpoints — ZERO events in the 30-min interior. So the stall SIGNAL condition
   (max-event-timestamp unchanged for >= 25 min) was genuinely present.

## The contradiction, and what it means

Points 1-4 together: the event stream was frozen for 30 min (4), the stall floor is
25 min (3), and the discovery + events + parsing path all work (1, 2). So the
watchdog SHOULD have confirmed STALLED at ~25 min and cancelled the run five minutes
before fabro's own turn timeout. It did NOT — the console journal carries zero
`stalled-no-progress` / `watchdog-stall-cancel` records ever on hp (foreman evidence
on `livespec-console-beads-fabro-4jb3kl`). **inferred:** therefore the failure is NOT
blanket discovery blindness. It is one of:

- **hung-state-specific discovery failure** (**hypothesis**): during a HUNG ACP turn
  the run's ps `status_kind` may not be `running`/`runnable` (so `_discover_run`
  returns None and hits the silent `continue`), even though a HEALTHY running turn
  shows `running`. A healthy run is NOT the same population as a hung run — untestable
  without a live hung specimen.
- **the `_watch` loop not executing / erroring on that path** (**hypothesis**): the
  launcher was engaged (foreman), but an exception or a code path that constructs
  `WatchedFabroLauncher` without running its `_watch` loop would produce the same
  zero-records signature.

Both are exactly what Child A's now-landed per-poll discovery observability captures
on the NEXT occurrence: it records, each poll, whether discovery matched and why not
(ps exit, row count, work_item_id match, status_kind). So the discriminator now
exists in production.

## Consequence for the cut

- **Research 003's root cause is DOWNGRADED**, not confirmed. Discovery works for
  healthy runs; the blanket ps-omission story is refuted. Do not implement B as a
  "fix ps discovery" change — ps discovery is not broken in the tested case.
- **B (`bd-ib-q5wxkh`) re-scoped**: its deliverable is to read Child A's observability
  from the next real hang (which records why `_discover_run` returned None, or that it
  matched and `decide_stall` still didn't fire), identify the actual hung-state
  mechanism, and fix THAT — whether it is a hung-turn `status_kind` the discovery
  filter rejects, a non-executing `_watch` loop, or (if the coarse signal proves
  inadequate) escalation to the 29f metrics-heartbeat. Still data-gated on the next
  hang; still needs the console foreman's standing `fabro ps -a --json --server hp`
  capture DURING the park to pin the hung-turn `status_kind`.
- **Child A was NOT wasted** — it is the instrument that (with these live probes)
  refuted the discovery-blindness cause and will pin the real one. This is the
  two-phase design working: instrument first, then fix with data.

## Verification-discipline note on THIS pass

The healthy-run measurement (point 1) rules out the BLANKET form of 003, but a
healthy run is a different population from a hung run — it cannot prove discovery
works DURING a hang. This dossier therefore downgrades 003 rather than declaring it
false, and names the hung-turn `status_kind` as the specific untested sub-condition.
