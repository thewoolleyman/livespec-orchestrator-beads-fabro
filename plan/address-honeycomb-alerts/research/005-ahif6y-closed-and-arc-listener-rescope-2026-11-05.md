# 005 — ahif6y closed, and the ARC listener trigger re-scoped (2026-11-05)

This note follows note 004. Each measurement below names its source so the
plan-level proof can re-run it.

## dolt-server-ahif6y is closed

- livespec-orchestrator-beads-fabro v0.288.0 was tagged at 10:38Z. It contains
  the `bd-ib-q3ejtp` fix (merge `ac3e184d3`). dolt-server's project plugin
  install was updated from `21c88ffdf840` to `44bc762b6610`.
- The saved `host_recorded` payload
  (`data/ahif6y-host-recorded-payload-2026-11-05.json`) was posted from that
  build onto dolt-server PR #162 at 10:39:42Z. The post resolved PR #162 from
  the journal's `reconcile-pr-selected` row.
- A separately started Codex replayer (session `01a1ab4c-ccef-7ca2-a5c9-682443b226c3`)
  re-measured all six assertions. It staged a fresh overlap: a manual run went
  from 11:45:31 to 12:09:55 CET, and the scheduled run went from 12:01:30 to
  12:04:50 CET. The scheduled run logged `sync already in progress (1154s)`,
  synced 14 of 15 and exited 0. Honeycomb query `gziTnFbJmbc` shows
  `backup-oversized outcome=skipped_in_progress`. The replayer posted
  `host_verified` on PR #162 at 11:13:22Z.
- The replay post's own reconcile drive then exited 3 with `ambiguous merged PR
  candidates for reconcile-merged: #161 ..., #162 ...`. Re-driving the same
  route with the selection named (`reconcile-merged --item dolt-server-ahif6y
  --pr 162`, gate `20261105T111456Z-1247335`, PASSED) closed the item at
  11:15:24Z.
- **A residual defect remains.** In `44bc762b6610`,
  `commands/_dispatcher_host_record_post.py` line 336 calls
  `seams.reconcile(work_item_id=item.id)` without the pull request the post
  already resolved. The rider comment on `bd-ib-q3ejtp` (11:18:30Z) records
  it. No new item was filed, because this was an unattended session with no
  filing consent.

## A new alert group: CI runner host has no ARC listeners (`4uMQfR6V2cr`, livespec)

This group was not in the 10-28 → 11-04 baseline. It began firing after
2026-11-05T09:54Z, and plan assertion 2 still requires it to be dispositioned.

- **The trigger read the wrong quantity.** It was `MAX(livespec.ci_listeners.active)`
  for `host.name = poweredge-xubuntu`, over 20 min, below 1. That gauge is a
  `/proc` count of `ghalistener` processes on the heartbeat host only (livespec-dev-tooling
  `ci-runner/observability/ci-runner-heartbeat.sh` line 129). The heartbeat
  is installed on the server node only.
- **Placement moved, nothing broke.** The listener pods carry no node
  constraint (`nodeSelector` is only `kubernetes.io/os: linux`, and there is
  no affinity). At 09:54:17Z ARC recreated all 12 of them, and every one was
  scheduled on `hp-xubuntu`. At that moment poweredge's load average was about
  100, so it was saturated. `kubectl -n arc-systems get pods -o wide` on
  poweredge, read at about 12:20Z, shows all 12 listeners `Running`, with 0
  restarts.
- **The cluster-wide control never dipped.** Source: livespec env, `metrics`
  dataset, 72 h, 20-min buckets. `COUNT_DISTINCT(k8s.pod.name)` with
  `k8s.namespace.name = arc-systems`, `k8s.pod.name ends-with -listener` and
  `k8s.container.ready = 1` read 11–12 throughout, with no dip; its only 0 is
  the partial first bucket. Meanwhile the per-host gauge fell from 12 to 0 at
  about 10:00Z.
- **Config updated** at 12:23:15Z (HTTP 200, `HONEYCOMB_CONFIG_KEY_LIVESPEC`).
  The trigger now uses that cluster-wide count over 20 min, below 1, with
  frequency 600 s and the same recipients. Its new name is "CI runner pool: no
  ready ARC listener anywhere in the cluster for 20 min", and its description
  carries the rationale. Fleet-wide zero listeners is still the alarm, and an
  empty window evaluates as 0, so a silent k8s_cluster emitter fires too.
  Per-listener readiness stays with the committed trigger "k8s ARC — a
  per-repository scale-set listener has no ready container for 5 min". The
  original definition is saved at `data/trigger-4uMQfR6V2cr-before-2026-11-05.json`.
  At its next evaluation it read `triggered=false` (Triggers API GET, 12:31:41Z).
- This trigger was live-only and never committed under livespec-dev-tooling
  `ci-runner/observability/triggers/`, so no committed definition drifts. Side
  observation, not filed: livespec-dev-tooling `ci-runner/README.md` (the
  `observability/` row) still describes "a listeners-below-1 value trigger"
  filtered to the heartbeat host.

## Live trigger state at about 12:20Z

Source: Honeycomb MCP `get_triggers` over livespec (51 triggers, both pages),
agent-activity (9), openbrain (1) and homelab (7).

- Two triggers read `triggered=true`. One is `EQMwDT61A6s` (post-hoc Red share,
  carried by `bd-ib-z2y4ca`). The other is `4uMQfR6V2cr`, read before the
  re-scope above.
- No trigger is disabled in livespec, agent-activity or openbrain. homelab's 7
  are disabled, which is exempt under the 2026-11-04T16:43:52Z deferral.
