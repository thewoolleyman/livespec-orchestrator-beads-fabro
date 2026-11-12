# 012 — Host CPU saturation re-scoped to vmi3006760; unattributed-billing trigger has an owner (2026-11-12)

Claude session 4b0efde5 (overseer resume, unattended), about 20:15–21:30Z on
2026-11-12. Handoff 37 named two Triggered mails from 2026-11-12 that no
research note 001–011 mentions. This note gives each one a disposition.

Honeycomb reads went through `tmp/7jmpyz-capture/hc.py` (gitignored, run under
the livespec env wrapper). The trigger read and write used the Honeycomb REST
API with the agent-activity Configuration key from `with-homelab-env.sh`, the
key note 002 lists under "Access facts". Mail reads went through the claude.ai
Gmail connector.

## Trigger sweep at 21:13Z

Read-only, with `tmp/plan-proof/sweep.py`:

| Environment | Triggers | Disabled | Reading triggered |
|---|---|---|---|
| livespec | 53 | 0 | `nak9miYrs14` bd-guard raw op; `EQMwDT61A6s` post-hoc Red share |
| agent-activity | 9 | 0 | `J1giUnNgJBV` dolt-backup dead-man |
| homelab | 7 | 7 (exempt) | none |
| openbrain | 1 | 0 | none |

- `EQMwDT61A6s` is owned by `bd-ib-z2y4ca` (open).
- `J1giUnNgJBV` is owned by `dolt-server-cudtkp` (open).
- `nak9miYrs14` was dispositioned in note 009: the condition is real, the
  trigger is correct, and it has no carrier. Its 60-minute window clears by
  itself. If the final sweep finds it triggered, re-read it after the window
  rather than count it against assertion 2.

## `mMmMEEKb7ZR` host CPU saturation (agent-activity): config updated

**Trigger as it was.** `AVG(system.cpu.utilization.idle) < 0.9` over a
30-minute window, evaluated every 15 minutes. The query had no filter and no
breakdown. It was created 2026-07-23 and never updated. It did not fire in the
2026-10-28 to 2026-11-04 baseline, so it is an out-of-baseline group, handled
like the groups in note 009. The full definition is saved in
`data/trigger-mMmMEEKb7ZR-before-2026-11-12.json`.

**What was wrong.** The description states the purpose: a host-usability
safety net for "the 18-core host", with 0.9 = 5% x 18 cores. Two hosts now
report to `livespec-host-metrics`:

- vmi3006760 has 18 cores (`nproc`). It is the development host.
- hp-xubuntu has about 16 cores (its highest idle reading over 60 days is
  15.95). It is a factory worker and sends about 2.5 times as many events.

So the trigger averaged both hosts. `bEVsU9BQw22` had the same defect and was
re-pointed per host in note 003.

**Measured.** All windows below are from 2026-11-12.

- The 19:36Z Triggered mail. Over 19:05–19:40Z the average idle was 0.52 on
  hp-xubuntu and 1.37 on vmi3006760. The blended average crossed 0.9 because of
  hp-xubuntu alone.
- 30 days of 30-minute buckets of `AVG(idle)`:

  | Scope | Buckets below 0.9 | Days |
  |---|---|---|
  | No filter (the old trigger) | 1 | 11-03 |
  | vmi3006760 only | 6 | 10-25, 11-03 |
  | hp-xubuntu only | 16 | 10-14, 10-16, 11-03, 11-04, 11-08, 11-09, 11-12 |

  The blended query both fires on factory load and hides real saturation of the
  development host: on 11-03 it caught 1 bucket where vmi3006760 alone had 4.

**Disposition: config updated.** Applied 2026-11-12T21:20:54Z with a PUT by id
(HTTP 200) and read back by GET:

- Added the filter `host.name = vmi3006760`.
- Renamed the trigger to "host CPU saturation (vmi3006760) — idle < 5%
  sustained 30 min".
- Appended the rationale and the measurement to the description, as plan
  assertion 1 requires.
- Unchanged: the calculation, the 1800 s window, the < 0.9 threshold, the 900 s
  frequency, the recipient `jKw2EyfLJ3W`, and the enabled state.

CPU saturation on hp-xubuntu is not a host-usability fault. The packed-fleet
revision (`alert-thresholds-match-packed-fleet`, livespec-dev-tooling spec
v144) deleted node-CPU saturation alerts for factory workers; see notes 003
and 006. No carrier is needed.

This trigger is not managed as code. A search of livespec,
livespec-dev-tooling, this repository, dolt-server and homelab (excluding
`.git`, `tmp`, virtualenvs and vendored trees) found only the archived handoff
of `livespec/plan/archive/fabro-ci-image-factoring`. The live edit therefore
causes no drift from a committed definition.

## `xfZgLzNAw3q` token-spend unattributed billing (livespec): owned, no action

- Created 2026-11-12T16:33:15Z, so it is out of baseline. It mailed at 16:45Z
  and 17:45Z, and it read not triggered at 21:13Z.
- Its description names the condition it caught: anthropic-2 drained
  2026-11-12 08:42–13:42Z with nothing booked to it. It also names its owner:
  plan token-spend-analysis and `livespec-dev-tooling-n277mo` (status `ready`
  at 21:00Z).
- **Disposition: real condition, owned.** It needs no change from this plan.
  If the final sweep finds it triggered while n277mo is open, it meets plan
  assertion 2's "owned by a named open work item".

## Also seen in mail on 2026-11-12 (owners already recorded)

Delegated-gate no-verdict (`donph5`), dolt-backup run failed (`cudtkp`), CI
sccache hit floor (`m5m2dl`), post-hoc Red share (`z2y4ca`), the RAM floor and
the dolt ledger probe (handoff 37).
