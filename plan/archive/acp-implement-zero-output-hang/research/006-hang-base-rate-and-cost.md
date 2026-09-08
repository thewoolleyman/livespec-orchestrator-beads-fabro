# Dossier 006 — base rate and cost of the genuine zero-activity hang: common and expensive

Base-rate note for plan thread `acp-implement-zero-output-hang` (epic
`bd-ib-b5dg`), compiled 2026-09-04. Answers the cost/benefit input to the Child B
(`bd-ib-q5wxkh`) re-cut decision that research/005 opened: is the genuine hang
rare (so detection + human escalation suffices) or common (so the outward-facing
D3 fabro fix is worth it)? Measured on the hp factory run history. Labels
**measured** / **inferred** as before.

## The discriminator that survives a dead sandbox

`active_time_ms` is a REAL per-turn measurement (only `tool_time_ms` is hardcoded
0 — dossier 001's cross-repo evidence pointer). A timed-out ACP turn with
`active_time_ms ~= 0` did nothing (the genuine b5dg zero-activity hang); one with
`active_time_ms ~= wall` did real work and still hit its node/turn ceiling (a
BUSY timeout — a distinct class the 2026-09-01 counter-specimen note assigns to
`wcuauj.2`, NOT to b5dg). This survives sandbox reaping, so the historical run
record can be classified even though the sandboxes are gone.

## Measured — base rate

Snapshot of the hp factory (`fabro ps -a --json --server hp`, 2026-09-04): 127
`failed` `ImplementWorkItem` runs.

- **21 of 127 (16.5%)** ended with an `agent.acp.timed_out` event — the
  zero-VISIBLE-output timeout signature (upper bound on the hang, since fabro is
  blind intra-turn per dossier 005).
- **106 of 127** failed for other reasons (setup failures, test/PR failures,
  ENOSPC, etc.) with no ACP timeout.

Classifying the 21 by `active_time_ms`:

- **14 are unambiguous WHOLE-RUN zero-activity hangs** (b5dg): every timing block
  shows `active_time_ms` of 0–190 ms against wall times of 33–240 minutes. The
  split is starkly bimodal — hangs sit at ≤190 ms, busy timeouts at ≥190,000 ms,
  a 1000× gap with nothing between — so the classification is not threshold-
  sensitive.
- **7 have run-level `active_time_ms` > 60 s.** Some are genuine busy timeouts —
  e.g. `01M10EKB` active 45 min / inference 40 min / wall 240 min; `01M19NCV`
  active 50 min; `01M0MV2S` active 24 min — real work that hit the node ceiling
  (`wcuauj.2`, not this plan).

Three known specimens fall exactly where expected: `01M16KMWY5` (dossier 001's
original catch; active 143 ms, wall 65 min), `01M17P0QHRH` (dossier 002's
specimen; active 0, wall 240 min), both flagged hung.

## Measured — my inspect-based method UNDERCOUNTS multi-turn hangs (caveat)

`01M1ES066` — the 2026-09-01 counter-specimen, recorded on the epic as a genuine
per-turn hang (its `review_fix` visit-2 turn measured from EVENTS: active 0,
wall 3600687 ms ≈ 60 min) — was classified "busy / no hung turn" by BOTH my
run-level and my per-turn inspect walk. The reason: its run-level `active_time_ms`
aggregates OTHER productive turns (≈110 min of real work across the run), and the
per-turn hang lives in the run's EVENT stage timing, which my inspect
`conclusion`-block walk did not surface. So:

- The events-stream stage timing is the AUTHORITATIVE per-turn source (what the
  counter-specimen used); an inspect-`conclusion` walk has a blind spot for a
  hung turn embedded in an otherwise-productive multi-turn run.
- Therefore **14 is a FLOOR, not an exact count.** The true b5dg count is ≥15
  (the 14 whole-run hangs plus the confirmed `01M1ES066` miss), and possibly more
  among the remaining multi-turn runs in the "busy" bucket whose per-turn EVENT
  timing was not examined here. Busy-timeout (`wcuauj.2`) is correspondingly ≤6.

This is itself worth recording: a future exact census must read per-turn stage
timing from `fabro events`, not the inspect `conclusion` aggregate.

## Measured — cost

The 14 unambiguous whole-run hangs burned, on their worst hung turn alone, 33 to
240 minutes of factory wall-clock each — total **≥1120 minutes (~18.7 hours)**,
and that excludes `01M1ES066` and any other multi-turn instances. One
(`01M17P0QHRH`) sat at the FULL 240-minute implement-node ceiling with
`active_time_ms = 0` — four hours of a factory slot doing literally nothing. Each
hang also parks on a human-gate/`needs-human` at the end, consuming operator
attention on top of the wall-clock.

## Inferred — decision import for the Child B re-cut

The genuine zero-activity hang is COMMON (≥14–15 occurrences in the hp run
history, ~11–12% of ImplementWorkItem failures) and EXPENSIVE (tens of minutes to
4 hours of wasted factory wall-clock per occurrence, plus a human gate). It is not
a rare edge case. That materially strengthens research/005's recommended path:
invest in the fabro-side D3 intra-turn liveness signal so a real fail-fast becomes
possible, rather than downgrading R1 to detection-plus-escalation only. The cost
of the hang (≈19+ hours of factory time in the measured window) dwarfs the cost of
the D3 fabro change. The downgrade-only posture (research/005 option 3) would
leave this recurring spend in place.

Choosing and prioritising the D3 fabro work remains a maintainer call (it is
outward-facing upstream-fabro work), but the base rate says the answer should be
"do it", not "live with it".
