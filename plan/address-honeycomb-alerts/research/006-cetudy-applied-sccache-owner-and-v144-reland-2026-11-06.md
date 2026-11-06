# 006 — cetudy applied, a new sccache alert given an owner, and the v131 revision re-landed as v144 (2026-11-06)

Claude session 397f12fb, an unattended overseer resume. It follows handoff 16 and note 005. Every read below was read-only, unless it says otherwise.

## 1. The poweredge k3s CPU share is applied (livespec-dev-tooling-cetudy)

- livespec-dev-tooling PR #3542 merged at 02:24:54Z as 366fe93f.
  - Drift check, then `just ansible-apply ansible/ci-pool.yml --limit poweredge-xubuntu --tags k3s_system_slice_cpu_weight`: ok=5, changed=2, failed=0, finished 02:27:04Z.
- Reads on poweredge-xubuntu at 02:27:13Z:
  - system.slice cpu.weight is 1000 (it was 100). kubepods.slice is 2813.
  - kubepods.slice cpuset.cpus.effective is 0-71, so no CPU is pinned.
  - k3s MainPID is 12027, with NRestarts=0. /readyz returns ok.
- The k3s cgroup's share under full contention:
  - 15.0 CPUs when every one of the 12 root-level peers contends (total weight 4813);
  - 17.9 CPUs against the four slices that actually contend (total 4013);
  - about 2.5 CPUs before the change.
- Correction to handoff 16: its baseline PID, 3594510, was stale. k3s had started fresh at 00:55:59Z.
- The full record and the revert line are on cetudy, in its comment of 02:28:13Z.
- Between 02:27Z and about 03:35Z:
  - the datastore p99 held at about 0.01 s (query frTNY3zciLP);
  - the node peaked at 71.48 CPUs in a single 5-minute bucket (query dv5FJ8MCNd4).

  That is not yet the 30-minute saturation window that cetudy's assertions 6 and 7 need.

## 2. A new alert group: HfK9RB9tZYp, the CI sccache hit floor on poweredge

- The live trigger sweep at about 03:30Z covered the livespec, agent-activity, openbrain and homelab environments.
  - HfK9RB9tZYp was the only triggered trigger. EQMwDT61A6s read not triggered.
  - The homelab seven are disabled and exempt.
- AVG(livespec.ci_cache.sccache.hit_ratio_5m) on poweredge-xubuntu held at about 0.95 all week.
  - It fell to 0 at about 2026-11-05T23:30Z.
  - At the same moment its datapoints rose from 1 to 6 per 30 minutes. The gauge emits only under traffic, so traffic rose.
  - Queries: afdnRmx39RZ and izwzmVgCb2.
- Cause:
  - bd-ib-dqxcsh, the fabro-currency session's work, moved thewoolleyman/fabro's `fork-gates.yml` and `carrier-build.yml` onto the fabro-k3s ARC runners. The first runs were at 22:48Z; the first success was at 23:54Z.
  - Both compile with `RUSTC_WRAPPER=sccache` against the read-only ci-sccache Redis.
  - The warm-cache populator warms only livespec-console-beads-fabro ("sccache: cache already holds a00b1eb6@1.92.0; no build"). So every fork compile misses.
- Ruled out:
  - a Redis restart: the pod is 19 days old with 0 restarts;
  - a console toolchain change: it is still 1.92.0, with no commits since 11-04;
  - the populate failures: the three failed populate jobs are the file-budget refusal that livespec-dev-tooling-243dzr carries.
- Not re-scoped: the gauge reads the whole Redis keyspace, so the trigger cannot exclude the fork without going blind. legacy-coordinator-agent agreed.
- The fleet-host guard refused `kubectl exec` (even `redis-cli INFO`), so Redis keyspace counters were not read. Pod state and job logs came from `kubectl get` and `kubectl logs`.
- Owner: livespec-dev-tooling-m5m2dl (the populator warms the fork).
  - The ci-cache-optimization seat filed it at 03:36:14Z, under plan ci-cache-optimization (epic livespec-dev-tooling-7zozck), on legacy-coordinator-agent's R301 route.
  - Its Definition of Done requires HfK9RB9tZYp back at OK with its query and threshold unchanged.
  - Carrier-map scope event of 2026-11-06T03:38:34Z: m5m2dl joins assertion 2's carriers.

## 3. The alert-thresholds revision never reached master; it is re-landed as v144

- kubernetes-observability (epic livespec-dev-tooling-s2aqob) measured at about 04:05Z that the live triggers matched unmerged commit 31b47cac, not master.
  - k8s-node-cpu-saturation was committed on master but absent live.
  - The factory quota trigger had a 2 h window live and 15 min on master.
- Cause: livespec-dev-tooling PR #3413 merged at 2026-11-04T18:30:34Z with only its propose commit, e7479fa7.
  - The revise commit (42f7cd23, v131) and the trigger commit (31b47cac) were pushed to `spec/alert-thresholds-match-packed-fleet` minutes earlier, but they were not in the merge.
  - This plan's note 003 and handoffs 4 to 13 recorded v131 as landed. That was false until today. Note 003 is now corrected.
- Remedy, on legacy-coordinator-agent's R301 order:
  - The proposal was re-revised on master v143 under delegated mode, with the same MODIFY resolution and the scenario co-edit. Decider: legacy-coordinator-agent, ACCEPT on digest 6cf6afe2. The independent read-only sonnet review found NO BLOCKERS at 04:02:07Z.
  - Landed in ONE pull request with 31b47cac's changes: livespec-dev-tooling #3562, merged at 04:56:12Z (e97bb101 spec v144; c5522046 triggers).
  - The heading-coverage gap set is unchanged: 163 gaps, the same hash, before and after.
- Converged at about 04:58Z:
  - master has no k8s-node-cpu-saturation.json, and the quota time_range is 7200;
  - live has no 2K4wKhXN2SL, and nBJML2UAgbm matches its committed definition.
- Leftovers, not filed:
  - Both the committed and the live quota-trigger descriptions cite "Spec v131". The clause now lives in v144.
  - The stale remote branch `spec/alert-thresholds-match-packed-fleet` still exists. Its commits are superseded by #3562, and they are not ancestors of master.
- Lesson for the plan's proof: a merged pull request does not prove that its last-pushed commits landed. Before any record claims a change "landed in #N", verify on master by content (a file present or absent, a field's value).
