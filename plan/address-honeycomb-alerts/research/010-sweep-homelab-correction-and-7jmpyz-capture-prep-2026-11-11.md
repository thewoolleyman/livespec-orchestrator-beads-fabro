# 010 — Afternoon sweep, a note-009 correction, and 7jmpyz capture prep (2026-11-11)

Claude session 7089a545 (an unattended overseer resume), about 12:25–14:00Z on
2026-11-11. Every read below is read-only. No trigger, host, cluster object or
ledger record was changed while taking them.

The harness Honeycomb MCP connection was down in this session. Every Honeycomb
read went to `https://mcp.honeycomb.io/mcp` over HTTP with the livespec key
`HONEYCOMB_MCP_API_KEY_LIVESPEC`, which the livespec 1Password wrapper injects.
The key was read inside the client process and never placed on argv.

## Correction to note 009: the homelab Floor triggers are still disabled

Note 009 says: "All seven homelab 'Floor' triggers are now enabled, which
resolves the conflict note 002 raised for them." **That is wrong.**

At about 13:30Z, `get_triggers` on environment `homelab` lists all seven
triggers with `disabled = true`. The detail view of `VGdKBFDqjp` (Floor 1,
dead-man) reads "Status: Disabled". Every one of the seven was last updated
between 2026-08-22T04:32:04Z and 04:32:33Z, so none has changed since note 002
read them as disabled.

They remain exempt from plan assertions 2 and 4 under the
2026-11-04T16:43:52Z deferral scope event. Under that deferral the homelab
rollout disarmed them on purpose and owns their deletion. **The final sweep
must apply that exemption.** It must not treat assertion 4 as met because the
triggers are enabled.

## Live trigger sweep, 2026-11-11 about 13:30Z

| Environment | Triggers | Disabled | Reading triggered |
|---|---|---|---|
| livespec | 52 (2 pages) | 0 | `EQMwDT61A6s` (post-hoc Red share). Its owner, `bd-ib-z2y4ca`, is open. |
| agent-activity | 9 | 0 | none |
| openbrain | 1 | 0 | none |
| homelab | 7 | 7, exempt (see above) | none |

Changes since note 009's 08:07Z sweep:

- `wFv7MbGL79` (Codex allowance near limit) now reads Not Triggered. Its threshold
  is `>= 97`, last updated 08:42:46Z, so it resolved after the 08Z weekly reset,
  as note 009 expected.
- `vnW13mLVzen` (CI warm cache stale) has cleared. Its carrier, `243dzr`, is
  still open, so this reading proves nothing about the fix.
- New trigger `HYGUS6cDKk3`, "k8s events dead-man — no Warning events for 3 h",
  environment livespec, dataset `k8s-events`, item `livespec-dev-tooling-a4rd4f`,
  created 2026-11-11T06:33:24Z. It was not in the baseline and reads not
  triggered.

## Cetudy assertions 6 and 7: still no saturation window

Query `mC5QLN8WKhG` ran `MAX(k8s.node.cpu.usage)` with the filter
`k8s.node.name = poweredge-xubuntu`, in 5-minute buckets from 07:00Z to 13:25Z
(78 buckets). Seven buckets reached 70 CPUs or more. The longest consecutive run
is four buckets, 09:55–10:10Z: 71.43, 70.69, 71.16 and 71.12. A qualifying window
needs six. The node has 72 CPUs, and its per-bucket MAX tops out at about 71.4.

## 7jmpyz: interim reading and assertion-1 evidence

**Build identity for the capture.**

- PR #3422 merged at 2026-11-04T19:58:28Z as `fc7d8c1416eb9f7aad2e140106f4ae1e7d15d8e3`.
- The first release containing that merge is `v1.173.0`, commit
  `52f8312e91bc3d4eb57cc812fcc2839155934189` (`merge-base --is-ancestor` exits 0).
- The live trigger `byh8SSQRjFe` matches
  `ci-runner/observability/triggers/ci-kueue-webhook-no-ready-endpoints.json`
  at that tag: MIN over 600 s, `host.name = poweredge-xubuntu`, threshold `< 1`,
  frequency 300 s.
- The live trigger was last updated 2026-11-04T19:07:51Z, and master has not
  changed the file since the tag.

**Interim reading of assertion 2, to about 13:30Z.**

- `MIN(livespec.ci_kueue.webhook_ready_endpoints)` for poweredge-xubuntu is 2,
  over 1,884 datapoints since 2026-11-04T19:08Z.
- Every 6-hour bucket carries datapoints.
- Trigger `byh8SSQRjFe` reads Not Triggered.
- On the live cluster, `kueue-webhook-service` has two endpoints,
  10.42.0.75:9443 on poweredge and 10.42.1.248:9443 on gmktec. Both
  kueue-controller-manager pods are 24 days old with 0 restarts.

**Assertion 1 re-measured.** These are 1-minute samples, MIN with
COUNT_DATAPOINTS. Every sample reads 2.

| Window | Query | Sample minutes |
|---|---|---|
| 2026-10-31 19:50–20:25Z | `515ZYGa7gDE` | 19:51, 19:56, 20:01, 20:06, **20:12**, 20:17, 20:22 |
| 2026-11-04 13:15–13:50Z | `nXCR9omSzj` | 13:16, 13:21, 13:26, 13:31, **13:37**, 13:42, 13:47 |

Each firing minute follows the only 6-minute gap in its window. That matches
the cause comment `01a1a7df` on the item: the probe timer drifts past the old
5-minute window, so the window is empty and evaluates as 0. No sample read 0.

**Capture plan.** The 7-day window closes at 2026-11-11T19:08Z. At or after
that time:

1. Post `host_recorded` on PR #3422 via `dispatcher.py post-host-record --repo
   /data/projects/livespec-dev-tooling --item livespec-dev-tooling-7jmpyz`, with
   the build block naming `v1.173.0`.
2. Have an env-stripped Codex replayer, started separately, follow the
   gitignored brief `tmp/7jmpyz-host-replay-brief.md` and post `host_verified`.

## Record rate

The 2026-11-11 record-rate warning fired at 8 entries against a threshold of 6.
The `diagnose-plan-progress:bd-ib-xkwdap` read was green, with no authorized
recovery operation. Nothing the plan is waiting on can be moved by a handoff:

- a time window: 7jmpyz at 19:08Z, and assertion 3's 72 hours;
- a load window: cetudy;
- other tenants' approval and dispatch valves: `donph5` and `sqo776` are
  pending approval; `243dzr`, `m5m2dl` and `bd-ib-z2y4ca` are ready.

So this note holds these findings instead of a separate handoff. The next handoff
follows the 7jmpyz capture.
