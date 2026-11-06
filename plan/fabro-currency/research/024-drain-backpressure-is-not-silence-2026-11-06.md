# 024 — A stalled log consumer is backpressure, not drain silence (2026-11-06)

Written by `claude:fabro-currency`, an unattended resume of plan epic `bd-ib-6tcjfx`, on
2026-11-06. It records work-item `bd-ib-aqcgxz`, the third of the five fork flaky-test items
(notes 022 and 023 cover the first two). All times are UTC.

The item's test is `fabro-petri`'s `a_large_output_round_trips_through_the_blob_table`. Under
host load it failed: the run ended `Success`, the output was not inline, and no record carried
a `blob://sha256/` reference.

Unlike the first two items, the cause was a PRODUCT defect, in Petri, not in the test.

## Cause

The test's command prints `OFFLOAD_THRESHOLD` (100 KiB) plus 512 lines of 9 bytes, so its
output is about 4.6 KB over the threshold. The output can only fail to offload if it shrank
below the threshold. The search for how it could shrink covered the Petri fork at
`fabro-integration-registered-20261023` `d25a6c15`, the commit the carrier's `Cargo.lock`
pinned:

- `OutputTail` in `crates/attractor/steps/src/command.rs` drops bytes in only three ways:
  - `OUTPUT_CAP`, which is 8 MiB, against an output of about 106 KB;
  - the executor's line cap, against 8-byte lines;
  - `ended_on_silence`.
- The executor pump (`crates/core/executor/src/lines.rs`) awaits every send and never drops a
  line.

So the drain must have ended on silence. `crates/core/steps/src/drain.rs` `Forwarder::finish`
stopped the forwarder once `DRAIN_IDLE_LIMIT` (5 s) passed with no line FORWARDED. The
forwarding future counted a line only after `logs.send(...)` returned.

Every command output line goes through the step's log channel (capacity 256) and the driver's
signal channel (capacity 1024) into the driver loop, which feeds it as a `StepProgressRecorded`
event. A loaded driver loop that held one send for more than 5 s therefore looked exactly like
a silent stream. The drain aborted the forwarder, and the step kept only what it had captured,
behind the truncation marker. Losing the tail took the output under the threshold, so it stayed
inline.

The module's own doc promised the opposite: "however slowly the log consumer takes it, re-arms
the limit, so a loaded run never loses the tail of a process that already exited". The process
step shares the same forwarder, so production command and process steps lost output tails
under load the same way. Upstream `lithoscomputer/petri` `main` has the same `drain.rs`.

## Fix

The Petri fix is `thewoolleyman/petri#4`, rebase-merged into
`fabro-integration-registered-20261023` at `c6bfd5e3`:

- `Forwarder::spawn` takes the line stream and a per-line `forward` closure.
- The forwarder records each receive, each hand-off, and whether it is waiting on the stream.
- `finish` ends `Silent` only after a whole idle limit spent waiting on a stream that yields
  nothing: the backgrounded-grandchild pipe the limit exists for.
- A consumer that never reads again is bounded by the run's own deadline.
- The drain tests run on a paused tokio clock.

The Fabro side is fork PR `thewoolleyman/fabro#33`, rebase-merged into `carrier-candidate-registered-20261023` at `41c42145e`. It bumps every
Petri crate in the carrier's `Cargo.lock` from `d25a6c15` to `c6bfd5e3`, and the `fabro-petri`
test itself is unchanged.

## Definition-of-Done repair (coordinator ruling R301, option C)

The item's third bullet asked for ten solo passes at load average above 90. No venue supplies
that load harmlessly; note 023 gives the reasons. The owning session replaced the bullet with
two:

- the shared drain keeps every line while its consumer holds one line for longer than the
  idle limit;
- ten consecutive solo runs on `fabro-k3s`, each with its job id and load reading.

## Evidence, all on `fabro-k3s`

| What | Run | Result |
| --- | --- | --- |
| Petri RED, `f7523d56` (refactor plus new test), branch `ci/petri-gate-aqcgxz` | `42193848962` | Only `a_consumer_stalled_past_the_limit_on_one_line_loses_no_line` failed: `left: Silent`, `right: Complete`. 31 of 32 `petri-steps` lib tests passed; fmt and clippy clean. |
| Petri GREEN, `1cbaa239` | `42194822949` | Drain 4 of 4. `petri-steps` 32 of 32. `petri-attractor-steps` lib 79 of 79 and `tests/steps.rs` 20 of 20, with the host sandbox plugin. fmt and clippy clean. |
| Fork gates on PR #33 head `c8d5d24f9` | `42195909423` | Format, Clippy and Test success: 4423 of 4423 passed and 60 skipped |
| Ten solo runs, branch `ci/solo-aqcgxz`, one archive built from PR #33's head | `42200805813` | 10 of 10 jobs passed, one at a time from 10:23:10Z to 10:35:05Z, each in 2.0 to 2.5 s. The 1-minute load average was 14.8 to 21.7 on 72-CPU nodes. Per-job ids and load readings are on the item. |
| First solo attempt | `42195946423` | Every job exited 127: the workflow installed no `cargo`, so the test never ran. Not evidence. |

Neither Fabro-side run is a RED for the test, and none can be made deterministic: the old
failure needed host load. The deterministic RED is Petri's paused-clock test.

The RED run's `petri-attractor-steps` failures came from a missing host sandbox plugin,
not from the change; the GREEN workflow builds it with `scripts/plugins-build.sh`. No fork
gate or build ran on vps. Both evidence branches carry throwaway workflows and are deleted
after the item closes.

## What the deploy slice still owes

Merging into the carrier deploys nothing. The serving build `85af3547e` still pins Petri
`d25a6c15`, so the fix reaches the factory only through a carrier build (`carrier-build.yml`)
and a gitops roll of the three gmktec instances. That slice is for the plan to schedule,
with the remaining fork items folded into one build.
