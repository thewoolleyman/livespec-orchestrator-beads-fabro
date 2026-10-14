## The maintainer's statement of what done means

ensure they get through the factory and get done correctly.

## Definition of Done assertions derived from that statement

- A factory run that exceeds the configured whole-run wall budget parks at needs_human with its work preserved and a budget-exceeded reason, and its slot is released.
- Over a 24-hour window on hp's fleet Fabro server after the change is released, no run holds a slot longer than the configured whole-run budget.

# Factory-run wall budget: origin, measurements and direction (2026-10-14)

Session: factory-run-wall-budget plan session (project livespec-orchestrator-beads-fabro), opened under
the coordinator directive of plan gitops-fleet-capacity-monitoring (livespec-dev-tooling, epic
livespec-dev-tooling-dfixhe). Adopted child: bd-ib-sdxfsn.

## The problem as filed

bd-ib-sdxfsn, measured by the coordinator on hp 2026-10-13 07:12Z-23:45Z at fleet cap 10: 45
ImplementWorkItem runs used about 120 slot-hours; 9 successes used 20.4 of them (median wall 99
minutes); runs ending at needs_human used 92.2. Runs that parked after implement (8 runs, 20.3 h),
pr (4, 14.0 h), proof_capture (2, 8.9 h) and fix (1, 4.6 h) each held a slot 200-390 minutes. Runs
that parked at dod_gate cost 0.3 slot-hours in total.

## Second measurement: the success distribution is wider than the median suggests

Measured 2026-10-14 00:30Z by this session with
`fabro ps -a --server https://hp-xubuntu.perch-rudd.ts.net:32276 --json` (589 rows, every workflow,
start times 2026-09-30T03:40Z to 2026-10-14T00:14Z), restricted to `ImplementWorkItem`.
`succeeded` means status kind `succeeded` (reason `completed`); a run that routes to the
needs_human node ends `failed` / `workflow_error` ("stage needs_human failed with no outgoing fail
edge", per the calibration rows of this repo's dispatch journal), so `failed` mixes needs-human
parks with genuine failures. Wall time is the run record's `wall_time_ms`, in minutes.

| Window start | Kind | Runs | p50 | p90 | max | Runs over 180 / 240 / 300 / 360 / 420 min |
|---|---|---|---|---|---|---|
| 2026-09-30 | succeeded | 156 | 86 | 192 | 506 | 18 / 7 / 2 / 1 / 1 |
| 2026-09-30 | failed | 288 | 65 | 245 | 548 | 66 / 34 / 13 / 6 / 3 |
| 2026-10-07 | succeeded | 94 | 85 | 172 | 348 | 8 / 3 / 1 / 0 / 0 |
| 2026-10-07 | failed | 245 | 65 | 254 | 548 | 58 / 31 / 12 / 5 / 2 |
| 2026-10-11 | succeeded | 60 | 101 | 192 | 348 | 7 / 3 / 1 / 0 / 0 |
| 2026-10-11 | failed | 120 | 55 | 291 | 548 | 33 / 22 / 10 / 4 / 1 |

Slot-hours a budget would have returned from the 245 failed runs since 2026-10-07 (sum of wall time
beyond the budget): 240 min -> 33.1 h, 300 -> 14.4 h, 360 -> 7.0 h, 420 -> 3.2 h.

The longest recent success is run 01M4TECDB6K03J0WBQ5C9G0XEF (bd-ib-zi5ygh, 2026-10-13, 348 min);
the longest in the window is 01M47ANKZS2CEED4H6FRH8KW5W (2026-10-06, 506 min).

What this changes. bd-ib-sdxfsn suggests "about twice the median" (about 200 minutes). That figure
would have parked 7 of the 60 successes since 2026-10-11 — healthy runs that merged. A budget is
therefore a trade between slot-hours returned and successful runs cut off, and the curve above is the
input to that trade. Load matters too: hp ran at load 25-38 on 16 cores through this window, and
sandbox `just check` time roughly doubled (plan stall-watchdog-false-kills research 001), so the
success tail is partly a load artifact and will move when the cap moves.

## What already exists (prior art, closed items included)

- No enforced whole-run deadline exists. `_dispatcher_execution_budget.py` derives the graph's
  worst-case ALLOWANCE (used for credential freshness, bd-ib-yx7pdm) and states that a sum of
  separately bounded operations is not a deadline anything enforces. The dispatch journal's
  `node-timeouts` row records `fabro_timeout_seconds` 145800 (40.5 h) — the `fabro run` subprocess
  ceiling of contracts.md §"ACP node timeouts", derived from the worst-case path, not a budget.
- Per-node timeouts are configurable (bd-ib-cnkf, closed): this repo sets implement 14400 s,
  review_fix 7200 s, fix and janitor 3600 s; the stall window is 7200 s (bd-ib-3ugnfr, closed).
- The host-side stall watchdog (`_dispatcher_watchdog.py`, Scenario 172) already owns a cancel path
  that journals a `watchdog-stall-cancel` record naming run, factory, stage, pull request and head;
  preserves work (resume from the published head, or a seed from a preserved commit); and rests or
  releases the item. A budget cancel is a second reason on the same rails, not a new pipeline.
- bd-ib-hnopf7 (closed) bounds a run PARKED in Fabro's human-input state past
  `dispatcher.blocked_run_grace_seconds`; it does not bound a run that is still executing.
- Plan stall-watchdog-false-kills (bd-ib-laf735) measured three healthy runs cancelled inside open
  command nodes. Its lesson binds here: a liveness signal is not a slot bound, and a cancel of a
  healthy run is the expensive direction.
- Plan agent-session-stall-prevention (bd-ib-jnpvh4) is about agent SESSIONS (plan sessions), not
  factory runs; nothing there governs this mechanism.

## Direction

Goal served: the maintainer's "ensure they get through the factory and get done correctly" —
capacity held by runs that will need a human anyway is capacity taken from runs that would finish.

1. A whole-run wall budget enforced by the Dispatcher's existing progress watchdog, as a new
   configured key beside the node timeouts (working name `dispatcher.run_wall_budget_seconds`).
   When a run's slot-holding time exceeds it, the Dispatcher cancels the run through the same path
   the stall cancel uses, journals a distinct budget-exceeded record (run, factory, stage, elapsed,
   budget, the layer that supplied the budget, pull request and head when published), and rests the
   item at blocked / needs-human with that reason and its work preserved. Cancelling the run is what
   releases the slot.
2. Guards against a false kill of a healthy run, each from a measurement above:
   - The clock counts slot-holding time — from the run's first `running` transition — never
     submission or queue time, because a queued run holds no slot.
   - The default is sized from the success distribution, not the median: no lower than the longest
     success of the trailing week (348 min). The proposed default is 21600 s (360 min), which would
     have cut off 0 of 94 successes since 2026-10-07 and 1 of 156 since 2026-09-30, and returns
     about 7 slot-hours a week at today's failure mix. A repository that wants a tighter budget sets
     the key; the curve above prices each choice.
   - A budget cancel is never non-convergence: it journals no `non-convergence-bounce` and feeds
     calibration no too-big signal, exactly as Scenario 172 rules for a stall cancel.
   - The budget must not be smaller than any single resolved node timeout on the run's path
     (implement is 14400 s here); a configuration that violates that is refused before any run
     exists, naming both keys, because a budget below a node's own ceiling cancels that node's
     legitimate turn.
3. Spec first. The behaviour is new and normative, so it is ratified through propose-change and
   revise as a contract paragraph plus a new scenario before bd-ib-sdxfsn is admitted; the child's
   Definition of Done references that scenario.

## Explicit deferrals

- "Fail late checks early" (the second half of bd-ib-sdxfsn's change). The bigger lever by the
  curve above, but it is a set of per-failure-class fixes — what makes a run park after implement,
  pr, proof_capture or fix — not one mechanism, and orchestrator-side failure classes are already
  owned by plan hp-factory-failure-follow-ups (bd-ib-qieqc6). Reconsidered when this plan's
  assertion-2 window is measured: every budget-exceeded park in that window is classified by stage,
  and any class that recurs is filed as a child of bd-ib-qieqc6.
- Re-sizing the Codex credential freshness requirement against the new enforced budget
  (`_dispatcher_execution_budget`, bd-ib-yx7pdm). An enforced budget would let the requirement
  shrink, but changing a credential gate is outside this plan's outcome; reconsidered after the
  budget ships, as a separate item if the coordinator wants it.
- Choosing the cap or a tighter budget value for hp. The fleet cap is maintainer-gated and owned by
  the coordinator (livespec-dev-tooling-uckxba); this plan ships the mechanism and a conservative
  default.
