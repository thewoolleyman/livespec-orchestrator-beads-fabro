# 025 — The fork's ci nextest profile kills no test for being slow (2026-11-06)

Written by `claude:fabro-currency`, an unattended resume of plan epic `bd-ib-6tcjfx`, on
2026-11-06. It records work-item `bd-ib-adrhkf`, the fourth of the five fork flaky-test items.
Notes 022 to 024 cover the first three. All times are UTC.

## Cause

`.config/nextest.toml` `[profile.ci]` terminated any test after `30s` × 4, about 120 s.
On 2026-11-03 at load average 100-113, four healthy `fabro-petri` hooks tests crossed that
limit and were reported as failures. They drive real git repositories and worker processes.

The config had a second gap. Nextest's precedence puts `profile.default` overrides above the
active profile's base. The `ci` profile therefore re-asserted its timeout for four packages,
but not for `fabro-proc` `binary(lifecycle)` (10 s × 3), which kept a 30 s kill under CI.

## Fix (fork PR `thewoolleyman/fabro#34`, rebase-merged at `c2be004f5`, config only)

- `profile.ci` sets `slow-timeout = { period = "30s" }` with no `terminate-after`, in its base
  and in ONE `filter = "all()"` override. The catch-all leaves no `profile.default` kill in
  force under CI.
- The fork-gates Test job gains `timeout-minutes: 120`. A cold build plus the full suite took
  about 17 minutes in run `42195909423`.
- The dev-host fallback recipe in `.ai/fabro-fork-hand-build.md` now wraps the nextest
  command in `timeout 2h`, because the detached gate runner has no wall bound of its own.
- No factory node runs fork tests.
- `profile.default` is unchanged; no gate uses it.

This follows the maintainer's ruling of 2026-11-03: the only time bound is the run-level one.

## Definition-of-Done repair (coordinator ruling R301, option C)

The bullet asking for five full runs at load average above 90 was replaced by two:

- the ci profile terminates no test for being slow, shown on a throwaway 125 s test;
- five consecutive full runs on `fabro-k3s`, each with its job id and load reading.

The bullet that each test still fails without its behaviour is met by a recorded read. #34
touches only `.config/nextest.toml` and `fork-gates.yml`, so `tests/hooks.rs` and the code it
exercises are byte-identical. Removing a kill cannot turn a failing assertion into a pass.

## Evidence, all on `fabro-k3s`

Run `42208040111` was on branch `ci/adrhkf-evidence`, with one `fabro-petri` archive built from
#34's head `382e23ff9` plus a throwaway `kill_demo` test that sleeps 125 s.

| What | Job | Result |
| --- | --- | --- |
| Throwaway 125 s test, OLD `ci` config | `127865567613` | `TIMEOUT [120.005s]`, 1 timed out |
| The same test, NEW config | `127865567591` | `PASS [125.007s]`, flagged SLOW |
| Full `--profile ci -p fabro-petri`, runs 1 to 5, one at a time | `127865566184`, `127865566283`, `127865566395`, `127865566186`, `127865566159` | each 214 of 214 passed, 4 skipped, no TIMEOUT; the four hooks tests took 0.75 to 3.89 s; the 1-minute load was 24.02, 19.21, 16.22, 12.52 and 12.33 on 72-CPU nodes |
| Fork gates on `382e23ff9` | run `42208092686` | Format, Clippy and Test success; 4423 of 4423 passed, 60 skipped |

The evidence branch was deleted after the item closed. No vps build ran.
