# 022 — The command stall tests run on a clock the command's output moves (2026-11-06)

Written by `claude:fabro-currency` (unattended Claude Code resume of plan epic `bd-ib-6tcjfx`)
on 2026-11-06. It closes work-item `bd-ib-oeckki`. That item covered the two fabro-petri stall
tests `command_output_refreshes_the_budget` and
`one_active_child_keeps_the_whole_parallel_run_alive`. Both measured their 1 s stall budget on
the real clock, so under host load they were cancelled although the run was active. It is the
first of the five fork flaky-test items the 04:00Z handoff listed. It is the first fork item
gated end to end on `fabro-k3s` (note 021). All times are UTC.

## Cause

Both tests ran through `case()` with no clock. The Petri stall watchdog therefore counted
everything on tokio's real clock against `stall_timeout="1s"`, including the time before the
command's first line, while the sandbox starts. About 1.7 s of start-up was observed at load
average about 70 on vps on 2026-11-04. This is the defect class of `bd-ib-gmuxd4` (fork #22).
That fix gave the watchdog an injectable `WatchdogClock` and drove the model-streaming case
with a `ManualClock`. Command (`parallelogram`) nodes do not go through a model adapter, so they
needed their own way to move the clock.

## Fix (fork PR #31, test-only)

- `lib/components/fabro-petri/tests/support/command_pace.rs` adds `OutputPace`, an
  `ExecutionObserver` passed to `engine::run_with_stall_clock`. It sees each record after the
  watchdog does. Each command output line is an engine record
  `StepProgressRecorded { ev: StepEvent::Log, .. }`, and each such record advances the
  `ManualClock` by a fixed gap. Nothing else moves the clock, so sandbox start-up and the
  script's real `sleep 0.2` take no stall time.
- The two tests run at a 200 ms gap and must end `Success`. They must also show more than 1 s
  elapsed on the manual clock.
- Two paired cases run the same graphs at a 1.5 s gap and must end `Cancelled` with
  `StallTimeout { stall_timeout_ms: 1000, idle_ms >= 1000 }`:
  `command_output_spaced_wider_than_the_budget_stalls` and
  `one_child_with_output_spaced_wider_than_the_budget_stalls_the_parallel_run`.
- The command nodes of those graphs drop `timeout="10s"`, because a command deadline runs on the
  real clock. The command default is 600 s, and the overall run timeout is the only time bound
  (the maintainer's ruling of 2026-11-03).

## Evidence, all on `fabro-k3s`

| Commit | Run | Result |
| --- | --- | --- |
| RED `25dbd26e1`, with a stub `OutputPace` that never moves the clock | `42166016151` | Format and Clippy success. Test failed: 3 failed of 2214 run (nextest fail-fast). The two success cases failed `elapsed() > 1s`; the first wide case ended `Success`, not `Cancelled`. No other test failed. |
| GREEN `77eae2c51` | `42167898218` | Format, Clippy and Test success: 4423 of 4423 passed and 60 skipped, two more tests than the 4421 of run `42132952719`. |

Merged by rebase into `carrier-candidate-registered-20261023` at `3aa7521ea` (series `2ef9ea8a5`,
`3aa7521ea`), verified by a content check on the carrier. No fork gate or build ran on vps.

## What is not done

- Not deployed. The change is test-only, so the serving engine `85af3547e` is unaffected. It
  rides into the next carrier build.
- Still parked as of this note: the four remaining fork flaky-test items, in id order
  `bd-ib-4uge7u`, `bd-ib-aqcgxz`, `bd-ib-adrhkf`, `bd-ib-sltfyg`. Each follows the same route.
