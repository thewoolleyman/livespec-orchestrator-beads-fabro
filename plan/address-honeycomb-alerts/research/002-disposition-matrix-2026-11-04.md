# 002 — Disposition matrix and first actions (2026-11-04)

Each control below was measured over 72 h ending about 15:50Z on 2026-11-04,
which is longer than every trigger's lookback. They come from Honeycomb queries
run in the opening session. The raw series JSON was fetched through each query's
`query_result_json` link and summarized per group.

## Matrix

| Group (trigger id, env) | 72 h control | Disposition | Carrier / action |
|---|---|---|---|
| RAM floor (`bEVsU9BQw22`, agent-activity) | Trigger read `AVG(system.memory.usage state=free)` averaged across BOTH hosts now in `livespec-host-metrics` (vmi3006760 and hp-xubuntu). The free series was below 8 GiB in 30% of 15-min buckets. Kernel-available memory never fell below 14.3 GB (hp) or 35 GB (vmi3006760). | **Config updated.** The trigger described the wrong quantity: free excludes reclaimable cache, and it mixed two hosts. | DONE 2026-11-04: re-pointed to `MIN(system.linux.memory.available)` grouped by `host.name`, same 8 GiB floor and 2-window rule, with the rationale in the trigger's description. The original definition is saved in `data/`. |
| CI runner fleet dead (`m82yfeYR2GX`, agent-activity) | Disabled since 2026-08-03 (provider spec v041 moved merge-gating CI to hosted runners), yet stuck at triggered=true. | **Deleted** (plan assertion 4). | DONE 2026-11-04 (HTTP 204). The full definition is saved in `data/` for restoration, which was the only reason it had been kept. |
| dolt-backup run failed (`9HKs4W3UYN8`) and dead-man (`J1giUnNgJBV`), agent-activity | Every hourly run since 2026-11-03 10:00Z exited 1. `CALL DOLT_BACKUP('sync','s3')` for `livespec-orch-beads-fabro` is cut at exactly 300 s ("connection was closed"), which matches `read_timeout_millis`/`write_timeout_millis: 300000`. The other 14 tenants sync. 31 unit_failure, 30 partial_failure, 0 run-level success. The 141 doltdb.service onfailure rows all date from the 11-01/02 deadlock (dolt-server-63etnh, closed). | **Cause fix.** This is a real defect, and THIS tenant's ledger has had no offsite backup for about 30 h. | Filed `dolt-server-ahif6y` (dolt-server tenant, pending-approval, no Definition-of-Done findings). |
| k8s node CPU saturation (`2K4wKhXN2SL`, livespec) | Idle below 10% in 28% (gmktec, hp) to 59% (poweredge) of 15-min buckets. Longest runs: 495, 375 and 165 min. The 12 h rolling average idle reached 0.011 on poweredge and 0.038 on gmktec. | **Config update needed, but SPEC-GOVERNED.** livespec-dev-tooling `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node telemetry" requires "a node whose CPU idle share stays at or below 10% for 15 minutes" as a value trigger. The fleet is packed to capacity by design. Harm is caught by the outcome triggers (Pending pods, OOM/CrashLoop, datastore latency, API readiness), and Pending never fired in 7 days. | Route a `propose-change` to livespec-dev-tooling: drop the 15-min CPU-idle trigger from the required set, or re-scope it to an outcome. Then apply via `ci-runner/observability/triggers/apply-triggers.sh` and delete the live trigger. A draft edit was discarded because `tests/livespec_dev_tooling/test_k8s_workload_control_plane_definitions.py` asserts the spec windows. |
| factory ResourceQuota ≥ 90% (`nBJML2UAgbm`, livespec) | factory requests.cpu was at or above 0.9 in 20% of buckets; longest stretch 75 min (factory-mi-homelab: 75 min at 1.0). No Pending-pod alert in 7 days. | **Config update, SPEC-GOVERNED** (same spec, §"Kubernetes workload and control-plane telemetry": "stays at or above 90 percent of its hard value for 15 minutes"). The Dispatcher packs to quota by design. | Same `propose-change`: a 2 h window keeps leak detection (cf. bd-ib-3i3j3k) and would have been quiet over this 72 h. |
| CI warm cache stale (`vnW13mLVzen`, livespec) | Over 3600 s in 21% of 10-min buckets; peak 23,129 s. | **Cause fix** (the populator misses its window). | Candidate existing carrier `livespec-dev-tooling-243dzr` (populate refuses every generation over a 20,000-file budget). Verify against the CronJob's REFUSED lines before naming it. |
| CI cache negative tests (`rxd7n9GVBYx`, livespec) | 7 failures in 16 runs over 96 h; live-triggered again since 12:50Z. | **Cause fix** (trust-boundary or broken-tier signal; never re-threshold). | No item found in livespec-dev-tooling. File one after reading the failing job logs. |
| Kueue webhook no ready endpoints (`byh8SSQRjFe`, livespec) | 1 zero reading at 5-min resolution in 72 h; fired 10-31 and 11-04 13:37Z. | **Cause fix** (each zero is a full admission outage; single replica). | No item found. Candidate cause: `bd-ib-y6v7b6` (the agent restart playbook can restart gmktec while kueue runs there). File a livespec-dev-tooling item after correlating the timestamps. |
| k8s datastore latency p99 > 1 s (`nhh3YgmhABN`, livespec) | 5 of 865 five-min buckets over 1 s; max 1.75 s; coincides with poweredge saturation. | **Cause fix** (kine/SQLite on a saturated control-plane node). | Candidate carrier `livespec-dev-tooling-qql3lo` (move the datastore to embedded etcd), or the pod-spread items `livespec-dev-tooling-mtvxde` and `bd-ib-plon2p`. |
| post-hoc Red share (`EQMwDT61A6s`, livespec) | 0.54 over 72 h (14,963 classified rows); every 8 h window was at or above 0.25. | **Cause fix**, owned by plan `bd-ib-q622ls`. | Carrier `bd-ib-z2y4ca` (that plan's typed required result). |
| Codex allowance near limit (`wFv7MbGL79`) / credits drawn (`ytMVcVZCawC`), livespec | Fired 11-03 23:33Z and resolved after the weekly reset (09:03Z). | **Real condition**, owned by the livespec-dev-tooling factory-spend track; the trigger matches reality. | Keep. Recheck at verification. |
| token-spend source quiet: factory emitter / Codex spans | One fire on 11-01 (factory idle about 3 h overnight). | Keep; recheck. | — |
| Delegated gate no verdict (`xMggkF8364A`) | One fire on 10-30. | Real condition; keep. | — |
| homelab "Floor" triggers (7, all disabled) | The homelab rollout disarmed them on purpose; they are deleted together with the `homelab` environment at that rollout's bankruptcy gate (homelab `archive/nixos-era-final/disposition-register.md` §C3: "Deletion is NOT this plan's to perform"). | **Conflicts with plan assertion 4** as worded. | Needs a maintainer call: wait for the homelab gate, or exempt the `homelab` environment from assertion 4. |

## Access facts

- `HONEYCOMB_CONFIG_KEY_LIVESPEC` (livespec wrapper) is a livespec Configuration
  key with triggers and recipients write access.
- `HONEYCOMB_TRIGGER_RECIPIENT_AUDIT_CONFIG_API_KEY` (homelab wrapper,
  `with-homelab-env.sh`) is an agent-activity Configuration key with triggers
  and recipients write access.
- livespec env triggers are committed as code in livespec-dev-tooling
  `ci-runner/observability/triggers/*.json`, converged by `apply-triggers.sh`,
  and several of their thresholds are fixed by that repo's specification. A
  live-only edit there drifts from the committed definitions
  (`livespec-dev-tooling-4vopaj`). The agent-activity triggers are live-only;
  dolt-server documents its own in `runbooks/alerting.md`.
