# 011 — RAM-floor and ledger-probe owners, and the cetudy window read from telemetry (2026-11-12)

Claude session 3f7c6fac (overseer resume), about 01:10–03:30Z on 2026-11-12.
Every read below is read-only. No trigger, host, cluster object or work item
was changed while taking them.

Honeycomb reads went through the harness Honeycomb MCP, which was up in this
session, and through `tmp/7jmpyz-capture/series.py` (gitignored, run under the
livespec env wrapper) for exact per-bucket series. Mail reads went through the
claude.ai Gmail connector. Host reads ran locally on vmi3006760, which is the
host this checkout runs on.

## Triggered mail since note 008

Search: `from:noreply@honeycomb.io after:2026/11/11`, Trash included. Note 008
covered mail up to about 2026-11-11T04:00Z. These groups have sent a Triggered
message since then:

| Group (trigger, env) | Triggered at (UTC) | Disposition | Owner |
|---|---|---|---|
| Codex allowance near limit (`wFv7MbGL79`, livespec) | 11-11 04:33 (resolved 09:03) | config updated to >= 97 at about 08:47Z (note 009) | none needed; fired before the threshold change |
| Delegated gate no-verdict (`xMggkF8364A`, livespec) | repeatedly, latest 11-12 00:53 (resolved 01:03) | cause fix | `livespec-dev-tooling-donph5` (pending-approval) |
| dolt-backup dead-man (`J1giUnNgJBV`, agent-activity) | 11-11 14:38 | cause fix | `dolt-server-cudtkp` (pending-approval) |
| dolt-backup run failed (`9HKs4W3UYN8`, agent-activity) | repeatedly, latest 11-12 01:59 (resolved 02:14) | cause fix; same 300 s sync cut as the dead-man | `dolt-server-cudtkp` |
| RAM-available floor (`bEVsU9BQw22`, agent-activity) | 11-11 09:01 and 20:01 (resolved 21:01) | config updated 11-04 (note 002); **the condition was real** | see below |
| dolt ledger probe (`CMatapHSRR7`, agent-activity) | 11-11 20:21 (resolved 20:25) | **not in the baseline** | see below |

The scope events up to 2026-11-12T00:10:20Z name `cudtkp` only for
`J1giUnNgJBV`. `9HKs4W3UYN8` has the same measured cause: every backup-sync
run since 2026-11-11T14Z ends `partial_failure`. So the same item owns it.

## RAM-available floor: a real breach on vmi3006760, owned by the /tmp leaks

`MIN(system.linux.memory.available)` grouped by `host.name`
(agent-activity/`livespec-host-metrics`, query `ukuDUUcXARP`; 7-day series
`CNqkBvFom7y`, 15-minute buckets from 2026-11-05T00Z):

- hp-xubuntu never went below 20.4 GB.
- vmi3006760 went below 8 GiB in 8 of 684 buckets, all on 2026-11-11:
  08:30–08:45Z (low 8.37 GB), 13:00Z (8.39 GB) and 19:30–20:30Z (low 7.45 GB).
  No bucket from 2026-11-05 to 2026-11-10 was below the floor.

So the trigger fired on a true, current condition. It is the
pause-for-provision signal its description names, and the re-pointing of
2026-11-04 is correct.

**Why vmi3006760 ran short.** Its `/tmp` is a tmpfs: `size=50%` of 94 GB, with
the `q /tmp 1777 root root 10d` tmpfiles age rule. Everything written there is
RAM. At about 02:55Z it held about 24 GB, and a `du -xd1` about 25 minutes
later read 28.3 GB. `free -g` at about 02:50Z read 71 used, 23 shared, 22
available. Container memory on the host is negligible: the four petri pods
read under 1 MB each (`d6n2DKpnHht`). The large /tmp entries at about 03:20Z:

| Entry | Size |
|---|---|
| `/tmp/claude-1000` (session scratch) | 9.8 GB |
| `/tmp/pytest-of-ubuntu` | 3.3 GB |
| `covns-full-tree-*` (10 dirs) | 2.2 GB |
| `livespec-orchestrator-beads-fabro-payload-*` (134 dirs, created 11-10 to 11-12) | 2.4 GB |
| everything else | about 10 GB, in hundreds of per-tool temp dirs |

These causes are already measured and owned by another plan:
livespec-dev-tooling plan `dev-host-disk-retention`, epic
`livespec-dev-tooling-qgwxo4`. On 2026-11-11 it measured `/tmp` at 86% at
13:27Z and moved 6.3 GB of leaked payload holders aside. Its open items for
the three largest leaks are:

- `bd-ib-immkx7` (this repository, ready): a launcher ended by a signal leaks
  its payload holder, because `release_payload` runs only from `atexit`
  (`.claude-plugin/scripts/bin/_payload.py`, `_bootstrap.py`). The leak runs at
  about 86 holders, or 1.4 GB, a day.
- `livespec-dev-tooling-64ik6g`: a SIGKILLed check runner leaks its `covns-*`
  coverage namespace directories.
- `livespec-dev-tooling-7tfa3x`: /tmp refills about 13 GiB in 9 h, while the
  session-scratch leg runs only daily.

Those three become assertion-2 carriers for `bEVsU9BQw22` in the carrier-map
scope event of 2026-11-12. This plan does not implement them; they close
through their own tenants' valves.

The tmpfs footprint cannot be traced back over time from Honeycomb. The host
receiver collects `/`, `/boot` and `/boot/efi` only, and `system.memory.usage`
carries no `shared` state. So the attribution above is to the measured
contributors, not to a measured per-minute series for 11-11.

## dolt ledger probe: one episode inside the RAM breach

`CMatapHSRR7` fires when the dolt-server ledger probe misses two consecutive
one-minute cycles. Over 7 days the environment holds exactly one
`outcome=ledger_probe_failure` event (`mVhgQb6BrcS`), at about 2026-11-11T20:20Z.
That is inside the 19:30–20:30Z window in which vmi3006760, the dolt-server
host, had under 8 GiB available.

Disposition: **coincident with the RAM breach, no separate carrier.** The
timing match is not proof of cause. The final sweep must re-check it, and a
recurrence outside a memory breach would need its own item.

## cetudy H4/H5: read from telemetry, no live window yet

The k3s server cgroup's CPU pressure has been in Honeycomb since
2026-11-10T19:50:54Z (`livespec.cgroup.pressure.cpu.some.avg60`,
`cgroup=system.slice/k3s.service`, livespec/`metrics`; carried by the closed
`livespec-dev-tooling-3gm5rb`). So H5 no longer needs a live ssh sample: it can
be read over any qualifying window after the fact.

- `MAX(k8s.node.cpu.usage)` for poweredge-xubuntu, 5-minute buckets,
  2026-11-10T19:50Z to 2026-11-12T02:50Z (`HHNmY7r5uLU`, 373 buckets): the
  longest run at or above 70 CPUs is 5 buckets (2026-11-11 16:45–17:05Z). No
  6-bucket window exists since the telemetry started.
- Load now plateaus around 64–71 CPUs. From 01:20Z to 02:45Z on 11-12 every
  bucket read 58.8–71.7, with runs of only 2 or 3 at 70 or above
  (`4FjysKkAxfh`).
- Over the same span, the k3s cgroup's some avg60 peaked at 3.83, against the
  H5 limit of 10. The datastore p99 (`P99(etcd_request_duration_seconds)`)
  stayed at or below 0.015 s (`zuMLVZF7dfy`, 1-hour buckets).

So the protection behaves as intended under near-saturation. The formal H4/H5
read still needs one 30-minute run at 70 CPUs or more, and it can now be taken
from Honeycomb whenever one appears. Whether a plateau just under 70 should
count is a question for `cetudy`'s own tenant, not for this plan.

## Effect on assertion 3

Assertion 3 needs a trailing 72 hours with no Triggered mail from a
dispositioned group. The RAM floor fired at 20:01Z on 11-11, and the
delegated-gate and dolt-backup groups were still firing after midnight. So the
window cannot start before their carriers land. Until the /tmp leaks above
close, the RAM floor will keep firing whenever vmi3006760's tmpfs grows under
heavy session load.
