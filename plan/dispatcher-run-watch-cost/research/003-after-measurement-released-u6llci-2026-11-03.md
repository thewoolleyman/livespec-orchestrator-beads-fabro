# 003 — The first after measurement: the released u6llci fix cuts about half, not 90 % (2026-11-03)

## What was measured

bd-ib-u6llci merged as PR #4223 (merge 2092ace07) on 2026-11-03 at 01:17Z, and it ships in v0.278.0 and v0.279.0. At
05:00Z the dev VPS ran 17 Dispatcher loops on mixed builds. Each loop's build was read from its payload path
(`/tmp/livespec-orchestrator-beads-fabro-payload-<version>-*/`), so one window could compare builds.

The sampler is the one reproduced in note 002, run unchanged: `measure_dispatcher_cpu.py 1200 <out.json>`.

## Result: 05:00:17-05:20:18Z (1,200 s), load average 38.6

15 loops watched a run for the whole window.

| Loops | Own CPU-s | Reaped-children CPU-s | CPU-s per live run per minute |
| --- | --- | --- | --- |
| 8 on v0.278.0 | 231.7 | 347.0 | 3.61 |
| 7 on v0.276.2 / v0.277.0 (2 idle) | 97.1 | 203.9 | 2.15 |
| all 15 (the sampler's own total, including live children) | 328.7 | 574.3 | 3.01 |

- The before figure is 7.18 CPU-s per live run per minute (note 002). The target is at most 0.72.
- The released build's 3.61 is about 0.50 of the before figure.
- The older builds measure LOWER than the released one in this window. That is run mix, not a regression: today's runs
  are young, so even a full-history events read is cheap. A 4-minute child sample at about 05:25Z put the old builds'
  full reads at about 1.4 CPU-s each.

## Where the released build's cost goes

- A 4-minute child-argv sample at about 05:25Z showed every v0.278.0 `fabro events` read carrying `--since`. The
  incremental read works. Each one still cost about 1.2 CPU-s (15 reads, 17.6 CPU-s).
- `fabro inspect` reads cost about 0.17 CPU-s of client CPU each. Each returns about 781 KB of JSON for the loop's own
  Python to parse on every poll.
- The loop's own Python is 1.45 CPU-s per live run per minute, twice the 0.72 target before any child is counted.
- Attached `fabro run` children cost about 0.07 CPU-s per minute each (2-minute sample at about 06:35Z, 9 children). They
  are not the floor.

## Read from the code at v0.279.0

- `_dispatcher_watchdog_observation.py`, `observed_run`: once a run is bound, every poll calls `port.inspect(run_id)`.
  `live_ps` (`fabro ps` without `-a`) serves only discovery before the run is bound.
- `_dispatcher_io_liveness_probe.py`, `_WallClockEventProbe.sample`: every poll calls `port.events(..., since=newest)`,
  whether or not the run changed.
- The poll interval is 60 s (`_WATCHDOG_POLL_INTERVAL_SECONDS`).

So plan assertion 3 is not met: a loop reads events on every poll, not only when the run needs it. Assertion 1's
"rather than from the run's event history" half is met, but status still comes from a 781 KB per-run record.

## Disposition

- On legacy-coordinator-agent's order, the follow-up bd-ib-22j24v was filed at P2 as a co-carrier of plan assertions
  1, 3 and 4. Each bound-run poll reads status and stages by id (`GET /api/v1/runs/{id}/stages`, about 21 KB; see the
  2026-11-02 23:26Z comment on bd-ib-u6llci). A poll whose status and stages are unchanged makes only that read. Events
  are read only at a stage boundary, a terminal state, or needs-human. It was approved to ready under the coordinator's
  R493 ruling and routed to legacy-dispatcher-agent for the P2 block.
- A single per-factory status listing for bound runs is deferred. Ratified Scenario 173 says a bound run's poll reads
  the run by its id and does not list the factory's runs. That design is reconsidered, as a propose-change, only if
  bd-ib-22j24v's by-id read misses 0.72.
- bd-ib-u6llci keeps its own acceptance. Its host-captured leg measures, and if it fails, its rework rider points at
  bd-ib-22j24v.
- The formal after figure for plan assertion 5 waits until every dev-VPS loop runs a released build carrying
  bd-ib-22j24v. It must be taken by the same note-002 method.
