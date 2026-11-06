# 026 — fabro-cli fixture setup waits with no wall-clock deadline (2026-11-06)

Written by `claude:fabro-currency`, an unattended resume of plan epic `bd-ib-6tcjfx`, on
2026-11-06. It records work-item `bd-ib-sltfyg`, the last of the five fork flaky-test items.
Notes 022 to 025 cover the other four. All times are UTC.

## Cause

`lib/apps/fabro-cli/tests/it/cmd/support.rs` bounded fixture setup by `command_timeout()`:
30 s locally, and 90 s when `CI` was set.

On 2026-11-04 at load average 45 to 117, `events_completed_run_outputs_raw_ndjson` and
`events_since_filters_output` failed at 32 to 37 s. Their fixture's `fabro run --dry-run` was
still running, so `fabro events` never ran.

The item listed seven deadline sites. There were EIGHT:

- an `assert_cmd` timeout on four commands: `run_success_in`, `run_completed_dry_run`,
  `setup_detached_dry_run` and `run_local_workflow`;
- an `Instant` deadline on four polls: `setup_detached_dry_run`, `wait_for_status`,
  `resolve_run`, and `wait_for_stream_item`. The last one, which `wait_for_run_finished`
  calls inside the dry-run setup, was the one missing from the list.

## Fix (fork PR `thewoolleyman/fabro#35`, rebase-merged at `bbe693847`, test-only)

- All eight deadlines are removed, along with `LOCAL_COMMAND_TIMEOUT`, `CI_COMMAND_TIMEOUT` and
  `command_timeout()`.
- The run-level bound is the fork-gates Test job's `timeout-minutes: 120`, from note 025.
- `std::thread::sleep` stays in each poll, so each `#[expect(clippy::disallowed_methods)]` is
  still fulfilled.

## Definition-of-Done repair (coordinator ruling R301, option C)

The `### Host-captured` bullet asked for ten runs on vps at load average above 90. It was
replaced by two:

- a recorded read showing that `support.rs` keeps no test-local deadline;
- ten consecutive solo runs on `fabro-k3s`, each with its job id and load reading.

## Evidence, all on `fabro-k3s`

Run `42217178027` was on branch `ci/sltfyg-evidence`.

| What | Job | Result |
| --- | --- | --- |
| Ten consecutive solo runs, each a separate nextest invocation of only the two tests | `127889987234` | 10 of 10 passed, 1.0 to 1.3 s per test, 12:36:37Z to 12:37:04Z; the 1-minute load average was 21.12 to 23.80 on a 72-CPU node |
| Targeted mutation: `--since` parsed then ignored, raw NDJSON never printed | `127889987036` | nextest exit 100, 0 of 2 passed. The raw test panicked on output that was not NDJSON, and the `--since` test failed its empty-stdout snapshot. The job went red only because its own `grep 'FAIL .*'` check ran against ANSI-coloured output. |
| Fork gates on `5b90f0d43` | run `42217218907` | Format, Clippy and Test success; 4423 of 4423 passed, 60 skipped |

## Not changed

`tests/it/cmd/install.rs` keeps its own 30 s `INSTALL_COMMAND_TIMEOUT` at nine sites. It is the
same class but outside this item's scope, so file it only if one fails in a measured run.

All five fork flaky-test items are now merged. Only bd-ib-aqcgxz's Petri fix changes engine
code, so the deploy slice is that one carrier build and roll.
