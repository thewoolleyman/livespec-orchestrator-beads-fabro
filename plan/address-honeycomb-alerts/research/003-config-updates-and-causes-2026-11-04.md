# 003 — Config updates applied and causes measured (2026-11-04, evening)

This note follows the matrix in 002. Every original trigger definition is
saved in `data/trigger-<id>-before-2026-11-04.json`.

## Applied

| Trigger | Change | Authority |
|---|---|---|
| `2K4wKhXN2SL` node CPU saturation (livespec) | Deleted | Revise of `alert-thresholds-match-packed-fleet`. CORRECTED 2026-11-06 (see 006): PR livespec-dev-tooling#3413 merged only the propose commit, so the v131 revision and the JSON removal never reached master. Both landed as spec v144 via livespec-dev-tooling#3562 (merged 2026-11-06T04:56:12Z; commits e97bb101 and c5522046). |
| `nBJML2UAgbm` factory ResourceQuota (livespec) | Window 15 min to 2 h (`time_range` 7200, frequency 1800), with the measurement recorded in its description | Same revision. CORRECTED 2026-11-06 (see 006): the committed JSON first landed in #3562 (spec v144), not #3413. The live trigger was updated in place by id, because applying by name would have created a duplicate after the name change. |
| `byh8SSQRjFe` Kueue webhook no ready endpoints (livespec) | MAX over 5 min changed to MIN over 10 min (frequency 300) | Measured cause below. No spec clause fixes its window. |
| `bEVsU9BQw22` RAM floor (agent-activity) | Re-pointed to per-host `system.linux.memory.available` | 002 |
| `m82yfeYR2GX` CI runner fleet dead (agent-activity) | Deleted | 002, plan assertion 4 |

## Causes measured

- **Kueue webhook: no outage.** I read one-minute samples around each firing: 2026-10-31 20:12Z, 2026-11-04 05:12Z and 2026-11-04 13:37Z. Each time the samples read 2 endpoints throughout, with a 6-minute gap between them. The probe timer is `OnUnitActiveSec=5min`, and it drifts. The old 5-minute MAX window went empty in the gap, and Honeycomb evaluated the empty window as 0. Both kueue-controller-manager pods show 0 restarts over 7 days. The evidence is on livespec-dev-tooling-7jmpyz.
- **CI cache negative tests: no breach.** All three failing runs fail only `warm-seed-private`, because `/__w/_warm/uv` is absent. The redis and proxy write refusals pass. Tracked in livespec-dev-tooling-fagyjw.
- **dolt-backup: real failure.** The livespec-orch-beads-fabro sync is cut at the 300 s listener timeout. Dolt 2.4.2 offers no per-session or per-listener override. dolt-server spec v030 (dolt-server#161) adds the verified on-host-copy exception, and dolt-server-ahif6y implements it.
  - Measured on this host: the stored-procedure copy to local disk took 19 s, the CLI restore 307 s, and `dolt fsck` 847 s with no problems.
  - The CLI S3 sync after the first 157 MB archive is latency-bound at about 4 KB/s. The cause is chunk-existence round-trips against a remote of 163 table files and about 1.04 M chunks. A single sync can therefore outlast the hourly cadence, so ahif6y now requires no overlap and per-step duration telemetry.
