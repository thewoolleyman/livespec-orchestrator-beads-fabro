## The maintainer's statement of what done means

We need to fix all the ongoing alerts that have crept up, either by resolving them or updating honeycomb/otel setup / config to match current reality.

## Definition of Done assertions derived from that statement

- Every Honeycomb alert group that fired in the 2026-10-28 to 2026-11-04 baseline has a recorded disposition: its underlying cause is fixed, or its trigger was re-thresholded, re-scoped or deleted to match how the fleet actually runs now, with the rationale written in that trigger's own Honeycomb description.
- At verification, no enabled trigger in the agent-activity, livespec, homelab or openbrain Honeycomb environments reads triggered, except one whose condition is real, current, and owned by a named open work item.
- Over a trailing 72-hour window under normal factory load, no dispositioned alert group sends a Triggered email.
- No disabled Honeycomb trigger remains in those environments: each one is either deleted or re-enabled against live data.

## Opening research — 2026-11-04 (alert baseline and approach)

### Why a plan, and how it relates to bd-ib-alerts

`bd-ib-alerts` is the STANDING alert-inbox triage tracker (never closed). A Codex
session flushed a RESOLUTION PLAN onto its description at 2026-11-04 14:52 UTC
and deliberately created no plan epic. That session's approach routed every
group to an owning track. On 2026-11-04 the maintainer invoked `plan` with the
slug `address-honeycomb-alerts` and asked for a plan: fix every ongoing alert,
EITHER by resolving its cause OR by updating the Honeycomb/OTel setup to match
current reality. This plan is now the formal carrier. `bd-ib-alerts` stays open
as the evidence log and the mail-cleanup procedure (its STANDING PROCEDURE,
Gmail boundary and Honeycomb access notes still apply).

The coordinator (legacy-coordinator-agent) ranks this plan priority 4 and
directs that factory-eligible children be ticketed through
legacy-dispatcher-agent at P4.

### Access path (verified this session)

- The Honeycomb MCP endpoint `https://mcp.honeycomb.io/mcp` answers JSON-RPC
  `tools/call` with `Authorization: Bearer $HONEYCOMB_MCP_API_KEY_LIVESPEC`
  under `with-livespec-env.sh`. The helper is
  `plan/archive/factory-success-rate-remediation/research/data/hctool.sh`.
  The response body is not strict JSON (raw control characters and `>`
  escapes), so parse it leniently.
- That key is a MANAGEMENT-type MCP key: it can READ triggers but cannot WRITE
  them. A trigger write needs an environment-scoped Configuration key. The
  livespec wrapper now also carries `HONEYCOMB_CONFIG_KEY_LIVESPEC` (present,
  scope not yet probed). The homelab-env key
  `HONEYCOMB_TRIGGER_RECIPIENT_AUDIT_CONFIG_API_KEY` is scoped to
  `agent-activity`. The first child must probe which key can write which
  environment before changing any trigger.
- Mail: the connected Gmail MCP works (`from:honeycomb.io newer_than:7d`
  returned 66 threads).

### Live trigger state at 2026-11-04 ~14:59 UTC

Triggers by environment: livespec 52, agent-activity 10, homelab 7 (all
disabled), openbrain 1, o11ycon2026 0.

Reading `triggered=true` right now:

| Trigger | Env / id | Note |
|---|---|---|
| CI cache negative tests failed | livespec `rxd7n9GVBYx` | re-fired 12:50Z today; the 06:03Z triage had called it quiet |
| livespec factory post-hoc Red share | livespec `EQMwDT61A6s` | 0.56 against 0.25 (72 h, 06:03Z); owner plan `bd-ib-q622ls` |
| dolt-backup dead-man | agent-activity `J1giUnNgJBV` | 4 successful runs in 24 h (06:03Z) |
| livespec host RAM floor < 8 GiB | agent-activity `bEVsU9BQw22` | flapping; re-fired 14:31Z |
| CI runner fleet dead | agent-activity `m82yfeYR2GX` | DISABLED, yet stuck `triggered=true` |

### Recurring or flapping groups in the 7-day mail baseline (2026-10-28 → 11-04)

Thread message counts give a rough sense of noise.

- k8s node CPU saturation, `2K4wKhXN2SL`: by far the noisiest (threads of 100,
  52, 42 and 30 messages). The factory deliberately packs hp-xubuntu with 4-CPU
  sandboxes, so "a node under 10% idle for 15 min" may simply describe normal
  full-factory operation. This is a re-threshold/re-scope candidate. Related
  capacity work: `bd-ib-plon2p` (CPU-pressure pod placement), `bd-ib-zl3qcz`
  (sandbox CPU limit), and owner plan `bd-ib-nmuyjc`.
- dolt-backup run failed, `9HKs4W3UYN8`: threads of 58 and 58 messages, with
  partial_failure and unit_failure rows. This is a genuine-cause candidate,
  owned by the dolt-server tenant.
- k8s factory ResourceQuota ≥ 90 %, `nBJML2UAgbm`: threads of 36, 34, 8 and 8.
  A full factory sitting near its quota is the design point, so this is a
  re-threshold candidate unless it predicts refusals. Note `bd-ib-3i3j3k`, a
  quota leak from orphaned cleanup pods.
- CI warm cache stale, `vnW13mLVzen`: threads of 20 and 20. The uv generation
  age peaked at about 23 k s.
- livespec host RAM floor, `bEVsU9BQw22`: threads of 15 and 14. Decide whether
  8 GiB is still the right floor for this dev host's current workload, or
  whether a leak exists.
- k8s datastore latency p99 > 1 s, `nhh3YgmhABN`: recurrent short spikes.
- CI runner host Kueue webhook no ready endpoints, `byh8SSQRjFe`: brief flaps.
- CI cache negative tests, `rxd7n9GVBYx`: intermittent failures.
- token-spend Codex allowance near limit (`wFv7MbGL79`) and Codex credits drawn
  (`ytMVcVZCawC`): fired, then resolved after the weekly reset. Owned by the
  livespec-dev-tooling spend track.
- token-spend source quiet (factory spend emitter, factory Codex spans): fired
  2026-11-01 05:49Z and resolved about 3 h later.
- Delegated gate: no verdict, `xMggkF8364A`: one fire on 2026-10-30.
- livespec factory post-hoc Red share: fired 10-30 and 11-02, and is live now.
- Disabled triggers: agent-activity `m82yfeYR2GX` (stuck triggered), plus all
  seven homelab "Floor" triggers. Each must be either deleted or re-enabled
  against live data.

Out of scope, by the maintainer's choice at creation: Honeycomb event-quota
overage. October used 126 M events against a 100 M plan, and burst protection
engaged on 2026-11-03 and 2026-11-04.

### Disposition approach

For each group, decide between two outcomes:

1. **Cause fixed.** The condition is real and unwanted. Route the fix to its
   owning track or tenant, using an existing item where one exists, and do not
   duplicate across tenants.
2. **Config updated.** The condition describes intended current operation, so
   the trigger is re-thresholded, re-scoped, given a longer window, or deleted.

Either way, write the rationale into the trigger's own Honeycomb description.
A group counts as quiet only when the live trigger is false AND a query over a
window longer than its lookback shows no recurrence. Email text alone is never
evidence.
