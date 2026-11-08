# 004 — Backup proof and carrier verification (2026-11-04, late evening)

This note follows note 003. Each measurement below names its source so the
plan-level proof can re-run it.

## dolt-server-ahif6y: proof of the oversized-tenant backup path

Both scheduled `dolt-backup.service` runs after the deploy of dolt-server
PR #162 exited 0 with `all syncs succeeded (15/15)`:

| Run (UTC start → end) | copy | restore | fsck | s3-sync | total oversized |
|---|---|---|---|---|---|
| 21:01:31 → 21:28:49 | 13,827 ms | 245,671 ms | 1,062,496 ms | 166,745 ms | 1,490,400 ms |
| 22:01:15 → 22:34:46 | 17,324 ms | 241,648 ms | 1,474,063 ms | 110,259 ms | 1,846,174 ms |

Honeycomb (env `agent-activity`, dataset `dolt-backup`, 20:55Z → 22:38Z) holds
exactly 2 `backup-sync` success events (15 of 15 synced, 0 failed, 0 skipped),
2 `backup-oversized` success events carrying the step durations above, and no
event of any other outcome.

The two runs are not independent of host load. `fsck` grew from 1,062 s to
1,474 s, and the whole run took about 33.5 min of the 60-minute cadence. If
`fsck` keeps growing, the per-tenant lock turns the overrun into a recorded
`skipped_in_progress` cycle instead of a second concurrent sync, and that
cycle shows in the `backup-oversized` telemetry.

Other Definition-of-Done checks, read on the host:

- `/etc/doltdb/config.yaml` lines 41–42 still read `read_timeout_millis: 300000`
  and `write_timeout_millis: 300000`.
- `dolt-backup.timer` is `OnCalendar=*-*-* *:00:00` with `RandomizedDelaySec=2min`.

The item was reconciled against PR #162 (`reconcile-merged --pr 162`, verdict
PASS). It is parked in `acceptance` while its host-captured leg is pending.

A third scheduled run (23:01:23Z → 23:32:26Z) also went green with 15 of 15
synced (fsck 1,284,341 ms).

**Overlap proof.** The first attempt missed. A manual `--db
livespec-orch-beads-fabro` run started at 22:37:57Z finished at 22:58:22Z,
because its fsck was quicker (about 15 min) than the earlier ones. That was
3 minutes before the next scheduled run. The second attempt worked. A manual
run (`dolt-backup-overlap-proof-2`) started at 23:50:10Z. The scheduled run
that started at 00:01:23Z logged ``oversized backup: `livespec-orch-beads-fabro`
sync already in progress (818s); not starting a second sync this cycle`` at
00:03:49Z. It then finished at 00:03:52Z with `all syncs succeeded (14/15;
skipped in progress: livespec-orch-beads-fabro)` and exit 0. Honeycomb
records a `backup-oversized` event with `outcome=skipped_in_progress` and
`holder_age_s=818`, plus a `backup-sync` success with `dbs_synced=14`,
`dbs_skipped=1` and `skipped_dbs=livespec-orch-beads-fabro`. (`skipped_cycles`
is a different counter: it counts hourly timer cycles a run's overrun
swallowed. It read 0.)

**Posting the proof is blocked by a tooling defect.** The `host_recorded`
payload covers all six assertions and is saved at
`data/ahif6y-host-recorded-payload-2026-11-05.json`. `dispatcher.py
post-host-record` refused it with "no single merged pull request resolves".
Two merged pull requests carry the item id in their titles: the spec PR #161
and the implementation PR #162. The host-record target resolver does not use
the `--pr 162` selection that `reconcile-merged` accepted. This is
`bd-ib-q3ejtp` bullet 3, the post-host-record half of that item, which has not
shipped (its reconcile half shipped in `3ddafa58f`). This was its third
measured instance, recorded there as a rider. Under stop-the-line nothing was
hand-posted; ahif6y waits in `acceptance` for that fix.

The superseded staging copy `/var/lib/doltdb/backup-staging-test` (3.2 GB, left
by the failed 17:22Z catch-up sync) was deleted after these green runs.

## Carriers verified for the two deferred groups

- **CI warm cache stale (`vnW13mLVzen`) → `livespec-dev-tooling-243dzr`.**
  Source: livespec env, `metrics` dataset, 72 h, 30-min buckets. Of 145
  buckets, 30 had `MAX(livespec.ci_cache.generation_age_s)` above 3600 s for
  `tier=uv` on `poweredge-xubuntu`. Every one of those stale stretches sits
  inside a run of `livespec.ci_warm.refused = 1`, with `generation_files` at
  21,088–25,828 against `budget_files` 20,000; `repos_failed` stayed 0 and
  `verified` stayed 1. That is exactly 243dzr's over-budget refusal. The most
  recent refusal was at 22:00Z today (22,963 files). The 22:30Z run published
  at 18,923 files, which is still within about 5% of the budget.
- **k8s datastore latency p99 (`nhh3YgmhABN`) → `livespec-dev-tooling-qql3lo`.**
  Same dataset, 72 h, 5-min buckets. 4 of 865 buckets had
  `P99(etcd_request_duration_seconds)` above 1 s, all on 2026-11-03 between
  15:20Z and 16:00Z (max 1.75 s). Over 15:00–16:30Z the k3s journal on
  `poweredge-xubuntu` holds 182 kine `Slow SQL` lines, so the cause is kine
  over SQLite. qql3lo moves the datastore to embedded etcd. poweredge's load
  average read 74.9 at the time of this check.

The carrier-map scope event of 22:45:09Z adds both items to assertion 2's
carriers and ends the deferral recorded at 18:08Z.

The coordinator held qql3lo at pending-approval as a maintainer item, because
it is a host migration plan rather than a small fix. Under R301 it directed a
read-only measurement child instead: `bd-ib-yqmnvi` (P4, host-routed through
`factory_safety: needs-host-only-input`). That child tests whether the kine
WAL is starved of checkpoints. Two `stat` samples taken about 23:05Z and at
23:09:28Z weaken that lead. The WAL stayed at exactly 195,803,032 bytes while
`state.db` itself was rewritten, which is what a WAL looks like when its
checkpoints run. The child is NOT a carrier and is not in the carrier map.

## Live trigger state at about 22:42Z

Source: Honeycomb MCP `get_triggers`, livespec (51 triggers, both pages),
agent-activity (9) and openbrain (1).

- Exactly one trigger reads `triggered=true`: `EQMwDT61A6s` (livespec factory
  post-hoc Red share), carried by the open item `bd-ib-z2y4ca` under plan
  `bd-ib-q622ls`.
- No trigger in those three environments is disabled.
- Every dispositioned trigger reads `triggered=false`: `J1giUnNgJBV`,
  `9HKs4W3UYN8`, `bEVsU9BQw22`, `byh8SSQRjFe`, `vnW13mLVzen`, `rxd7n9GVBYx`,
  `nhh3YgmhABN`, `nBJML2UAgbm`, `wFv7MbGL79`, `ytMVcVZCawC` and `xMggkF8364A`.

## What stands between this plan and its proof

Plan assertion 3 needs a trailing 72 h window under normal factory load with
no Triggered email from any dispositioned group. Two carriers still have live
causes. The warm cache refused as recently as 22:00Z today, so it can fire
again until 243dzr lands. The datastore p99 has been quiet since 2026-11-03
16:00Z, but its structural fix (qql3lo) is a backlog epic. Neither one is
fixed by a trigger change, so the earliest clean window starts after 243dzr
merges.
