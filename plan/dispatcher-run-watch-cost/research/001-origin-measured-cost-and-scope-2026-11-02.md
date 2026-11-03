## The maintainer's statement of what done means

Maintainer, attended, 2026-11-02, relayed verbatim by legacy-coordinator-agent: "Any reason not to do the cheap fabro ps alternative?  IF not get it done asap, on a focused plan, not fabro currency,". Definition of Done as the coordinator's brief states it, verbatim: "the dispatcher's run watch reads status for all live runs of a factory with one `fabro ps --json` (or equivalent status call) per tick and reads events only incrementally (since the last seen instant) and only when a run needs it (terminal state, needs-human, watchdog); measured VPS CPU per live run before and after on the dev VPS; no full-history `fabro events` read in the steady-state loop."

## Definition of Done assertions derived from that statement

- On the dev VPS, each Dispatcher loop watching a live factory run learns that run's status and terminal state from one Fabro status read per factory per poll tick, such as `fabro ps --json` or an equivalent status call, rather than from the run's event history.
- In the steady-state watch loop, no Dispatcher process issues a `fabro events` read that requests a live run's whole event history; after a process's first read of a run, each later events read of it requests only events since the newest instant that process already observed.
- A Dispatcher loop reads a live run's events only when the run needs it: when the run reaches a terminal state, when it needs a human, or when the stall watchdog takes its sample.
- The stall watchdog still reports a command node that started before the incremental read boundary and has not completed, and still cancels a run whose events stop for its whole stall window.
- On the dev VPS, the CPU-seconds per live run per minute that the Dispatcher loops spend, counting their own processes and their Fabro children, is measured after the change by the same method as the 2026-11-02 19:10Z baseline of 7.6 CPU-seconds, and the after figure is at most one tenth of the before figure.
- The Dispatcher loops running on the dev VPS run a released plugin build that carries the change.

# 001 — Origin, measured cost, and scope (2026-11-02)

## Origin

The maintainer asked this, attended, on 2026-11-02, relayed verbatim by legacy-coordinator-agent: "Any reason not to do the
cheap fabro ps alternative?  IF not get it done asap, on a focused plan, not fabro currency,". The plan sits under the
maintainer's priority 2, load on the development VPS. The seat reports to legacy-coordinator-agent.

## The problem, measured

- Each `dispatcher.py loop` on the VPS watches its run in `WatchedFabroLauncher._watch`
  (`commands/_dispatcher_io_fabro_launcher.py`). Every 30 s it issues one `fabro inspect <run>` and one
  `fabro events <run> --json` with no `--since` and no `--tail` (`_WallClockEventProbe.sample` in
  `commands/_dispatcher_io_liveness_probe.py`, through `FabroPort.events`). So every poll re-downloads and parses the run's
  whole history.
- One full read of a 3,122-event run is 8.56 MB: 38 s wall and about 4.5 CPU-s. The 0.393 client is no cheaper.
- Baseline, 2026-11-02 19:10:37-19:11:37Z (60 s), measured by /proc accounting of every loop and every child it reaped. 15 loops, each
  watching one run, used 57.8 CPU-s in their own Python and 57.0 CPU-s in their `fabro` children. That is 7.6 CPU-s per
  live run per minute, about 1.9 cores in total, on a VPS at load 40-52 on 18 CPUs. The sampler is reproduced verbatim in
  research note 002, so the after leg runs the same method; note 002 also records the formal 20-minute before figure: 7.18 CPU-s per live run per minute, 19:00:34-19:20:34Z.

## Does anything need the full history? (answered before filing)

No, not on the per-poll path. The poll's events read feeds exactly two values:

- `parse_last_event_epoch`, the newest event instant;
- `open_command_node`, a command node that started and has not completed. This is the Scenario 173 watchdog.

Both carry forward across polls in process state, so only a loop's first read needs history. The whole-stream readers off the
poll path already run once per dispatch, at the end:

- `watchdog_run_reading`, before a stall or wall-budget cancel;
- the cost chain, the review gate, the Fabro second reads, preserved-tree escalation, and the ACP availability probe reading.

They stay as they are. Endings and needs-human come from run STATUS, which `inspect`, or `ps` without `-a`, answers.

## Cheap alternatives, measured 2026-11-02

| Read | Size | Client CPU | Wall |
| --- | --- | --- | --- |
| `fabro ps --json`, no `-a` (13 live runs) | 209 KB | 0.37 s | 13.8 s |
| `fabro ps -a --json`, now 196 runs | 2.3 MB | 1.5 s | — |
| `fabro inspect <run> --json` | 781 KB | 0.22 s | — |

- Avoid `ps -a`: it has grown with the factory's retained history.
- `fabro events --since <window>` is filtered on the server, so its size scales with the window. During a burst on run
  01M6EPRPVNYJV2FCSJZB2TGH88, `--since 3m` returned 3.3 MB for 3.1 CPU-s. The burst was about 640 events a minute, recorded
  18:56:57-19:06:20Z; legacy-dispatcher-agent measured about 50 a minute from 19:05 to 19:17Z. Incremental windows are
  usually small but can burst.

## Children

- bd-ib-u6llci, re-parented from fabro-currency, carries the fix. It reads status once per factory per tick, reads events
  incrementally, spaces polls at 60 s or more unless status changed, keeps the watchdog's open-node report, and has a
  host-captured CPU leg of at most one tenth of the before figure. It was raised to P1 and handed to legacy-dispatcher-agent
  for the head of the priority-2 block. Its References line now also names Scenario 173.
- bd-ib-2dlh7m, re-parented from fabro-currency, bounds every other `fabro events` caller: failed-read backoff, no ACP
  projection re-reads, bounded reconcile, and a per-factory concurrency cap. It has been blocked needs-human since
  2026-10-22, with partial work preserved on `refs/heads/needs-human/93614d0b36c54696b8aa096afd83d1c8`. Its first assertion
  overlaps u6llci on the watch path only. Its fate is decided once u6llci lands: re-dispatch it rebased onto u6llci, or
  narrow it to the reconcile-side reads.
