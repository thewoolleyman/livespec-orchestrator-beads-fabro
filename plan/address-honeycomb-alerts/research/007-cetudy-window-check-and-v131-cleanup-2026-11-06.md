# 007: no cetudy saturation window yet; the v131 citations are corrected and the stale branch is deleted (2026-11-06)

Claude session a751905b, an attended resume. It follows handoff 18 and note 006. At about 06:28Z, legacy-coordinator-agent
answered this session's next-step picker under R301 (delegated authority, not the maintainer's own answer). It ordered:

1. Check now for a cetudy saturation window.
2. Then clean up the leftovers.
3. Then take the recorded bounded wait for livespec-dev-tooling-fagyjw's 48-hour check.

## 1. No 30-minute window on poweredge at 70 CPUs or above (cetudy assertions 6 and 7 still open)

- One targeted query ran in livespec/metrics: x3cbaCKPjn3, from 2026-11-06T02:27Z to about 06:29Z, in 5-minute buckets.
  - It read MAX(k8s.node.cpu.usage) filtered to k8s.node.name = poweredge-xubuntu.
  - It read P99(etcd_request_duration_seconds), the same datastore read as frTNY3zciLP.
- Only one bucket reached 70 CPUs: 02:50Z, at 71.48. The next highest were 64.04 (03:40Z) and 62.51 (03:20Z). After
  04:00Z, no bucket went above 52.12 (05:25Z).
- The datastore p99 stayed at or below 0.015 s in every bucket.
- So no window of 30 minutes or more (six consecutive buckets at 70 or above) has occurred since the apply.
  Assertions 6 and 7 cannot be graded yet, and the revert proof (assertion 8) is not started.
- When load comes back, re-run the same query and look for six consecutive buckets at 70 or above.
  Then read k3s.service cpu.pressure some avg60 on the host for that window.

## 2. The "Spec v131" citations are corrected to v144

- On master, v131 is the homelab-worker-nodes revision (7ef84779), not the alert-thresholds revision. So "v131" was a
  wrong pointer as well as a stale one.
- Two places cited it, and both are corrected in livespec-dev-tooling PR #3578:
  - the description of `ci-runner/observability/triggers/k8s-factory-quota-near-hard.json`;
  - `ci-runner/observability/README.md` (the packed-pool sentence).
- Only the citations changed. The query, the threshold and the 2-hour window are unchanged, and the description is 962
  characters, under Honeycomb's 1023 limit.
- `apply-triggers.sh` has no read-only drift mode yet, and it converges every definition in its directory. So the live
  update applies only this one trigger: the script runs from a scratch copy that sits beside this one definition. That
  keeps a full converge from overwriting any live hand-edits another session made.
- #3578 merged at 2026-11-06T07:07:56Z, with 13 checks passing and 1 skipped. Master was then checked by content: the
  quota definition cites "Spec v144 §", and `ci-runner/observability/` no longer contains "v131".
- The single-trigger apply answered `updated nBJML2UAgbm`. Reading the trigger back from the live API showed:
  - its description equals the committed one, contains "Spec v144", and no longer contains "v131";
  - its threshold is `>= 0.9` and its `time_range` is 7200, unchanged;
  - its frequency is 1800, the same as committed;
  - it is not triggered and not disabled.

## 3. The stale branch `spec/alert-thresholds-match-packed-fleet` is deleted

- Before deleting it, the branch was confirmed superseded by content, not by ancestry. This repository rebase-merges, so
  every `spec/*` branch reads as unmerged by ancestry.
  - `SPECIFICATION/history/v144/proposed_changes/alert-thresholds-match-packed-fleet-revision.md` is on master.
  - Its tip, 31b47cac, has the same quota trigger and the same workload definitions test as master.
  - Master's quota `time_range` is 7200, and `k8s-node-cpu-saturation.json` is absent from master.
- The branch was deleted at about 06:32Z (`git ls-remote` now returns nothing for it).

## 4. Still open

- Gmail cleanup: the 12 threads kept on 2026-11-05 (the datastore trio and EQMwDT61A6s) can be trashed. Keep only
  HfK9RB9tZYp. This needs a session with Gmail access.
- livespec-dev-tooling-fagyjw: capture its 48-hour check at or after 2026-11-06T22:35Z.
- cetudy assertions 6 to 8, 243dzr (merge, deploy, then the 72-hour quiet window), the 7jmpyz 7-day check around
  2026-11-11T20:00Z, m5m2dl (HfK9RB9tZYp), and bd-ib-z2y4ca (EQMwDT61A6s).
