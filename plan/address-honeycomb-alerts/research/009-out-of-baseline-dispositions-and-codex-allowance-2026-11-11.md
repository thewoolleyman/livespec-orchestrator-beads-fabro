# 009 — Out-of-baseline dispositions, live sweep, and a third "keep" row (2026-11-11)

Claude session 05ad9d45 (an unattended overseer resume), about 07:00–08:15Z on
2026-11-11. Every read below is read-only. No trigger, host or ledger record was
changed while taking them.

## Live trigger sweep, 2026-11-11T08:07Z

Source: `get_triggers` on all four environments through the livespec MCP key.

- **Assertion 4 (no disabled trigger).** Zero disabled triggers. The counts are
  livespec 50, agent-activity 9, homelab 7 and openbrain 1. All seven homelab
  "Floor" triggers are now enabled, which resolves the conflict note 002 raised
  for them.
- **Reading triggered:**
  - `vnW13mLVzen`, CI warm cache stale. Its carrier, `livespec-dev-tooling-243dzr`, is open.
  - `EQMwDT61A6s`, post-hoc Red share. Its carrier, `bd-ib-z2y4ca`, is open.
  - `wFv7MbGL79`, Codex allowance near limit. It has no carrier; see the next section.

## `wFv7MbGL79` (Codex allowance near limit) is a third "keep" row that blocks assertion 3

Note 002 dispositioned `wFv7MbGL79` as "real condition … the trigger matches
reality. Keep." Note 008 listed only two "keep" rows (Delegated gate
no-verdict, and token-spend source quiet), so this one was missed.

Measured. Source: livespec `llm-spend`, `MAX(codex.used_percent)` where
`kind = "codex-allowance"`, with 1-hour buckets (queries `kZbdQNa8jWn`, plus a
14-hour re-read):

| Instant (UTC) | used percent |
|---|---|
| 2026-11-03T22:00 | 90 (trigger fired at 23:33Z) |
| 2026-11-04T08:00 | 2 (weekly reset) |
| 2026-11-10T19:00 → 2026-11-11T07:00 | 83 rising to 92; 90 was crossed at 04:00 |
| 2026-11-11T08:00 | 0 (weekly reset) |

`SUM(codex.credits_drop)` was 0 throughout, so no paid credits were drawn.

Why this happens by design: the dispatcher's Codex headroom brake allows Codex
to run down to 5% remaining within 12 hours of the weekly reset. The constants
are `RELAXED_CODEX_FLOOR_PERCENT = 5` and
`CODEX_RESET_PROXIMITY_SECONDS = 43_200`, in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_acp_codex_headroom.py`.
A trigger set at 90% used therefore fires once every week, inside the window in
which the factory is meant to finish spending the allowance. That is normal
factory load, so assertion 3's trailing 72 hours cannot be quiet across a
weekly reset while the trigger keeps its current threshold.

The disposition is a **config update**, and the trigger's owner has to make it.
The trigger description names plan factory-spend-accuracy and board
`abHcUYvjaYf`, and the token-spend-analysis seat owns it. Two candidate fixes:

- Raise the threshold above the relaxed floor (for example, at or above 96%
  used). It then fires only when the brake has failed to hold.
- Delete it as redundant. The paid-credit signal `ytMVcVZCawC` (credits drawn
  `> 0`) already reports the harm this trigger predicts.

This plan does not write another seat's trigger. The finding goes to
legacy-coordinator-agent under the same routing rule (R301) that handled the two
earlier "keep" rows.

## Out-of-baseline groups from note 008: measured dispositions

None of these five groups was in the 2026-10-28 → 11-04 baseline. Each one
falls under assertion 2 at verification: it must be either quiet, or real,
current and owned.

| Group (trigger) | Measured | Disposition |
|---|---|---|
| k8s controllers zero available replicas (`zZqzbKYnzZf`) | Over 10 days, `MIN(k8s.deployment.available)` broken down by deployment shows exactly ONE real zero: `ci-runner-scheduler`, in the 5-minute bucket at 2026-11-09T08:30Z. The other four deployments never reached zero; their 11-01T08:00Z rows are the empty first bucket of the query range. Kueue's minimum was 2. `ci-runner-scheduler` was added to this trigger on 2026-11-07. | **Real condition; trigger correct.** One isolated gap of about 8 minutes, and at zero, runner pods fail open to the default scheduler. No carrier. Recheck at the final sweep; if it recurs, file a livespec-dev-tooling item for its single replica. |
| bd-guard raw non-conformant bd op (`nak9miYrs14`) | 10 days of `guard.warned = true`: 2 events, both raw `bd update … --status in_progress` calls from agent sessions (one on `hl-x9w`, one on `bd-ib-y6v7…`). Both were blocked (`guard.mode = fail`). | **Real condition; trigger correct.** It names a caller that bypassed the lifecycle and was stopped. It is rare, and the 60-minute window clears by itself. No carrier. |
| token-spend quiet: caam reads (`9PRVAXHJoeJ`) | Hourly `kind = "caam-read"`, 4 days: one gap, 2026-11-10 from 15:00 through 18:00Z; continuous since 19:00Z. | **Real condition outside normal load.** The gap coincides with the 11-10 cap outage. The owning seat ruled the same window on `e1skfYAgWqC` a true condition, kept unchanged (scope event of 2026-11-11 about 04:50Z). No carrier. |
| token-spend quiet: local account attribution (`k2wXDHgSjRA`) | Hourly `spend.account_source = "caam-active-timeline"`: one gap, 2026-11-10 at 18:00Z; continuous since 19:00Z. | Same as the row above. |
| token-spend quiet: local Claude/Codex emitter (`mdBC2K19hfG`) | Hourly `spend.where = "local"`: no missing hour. Counts fell from about 1,000–1,600 an hour to 145, 119, 8 and 1 between 15:00 and 18:00Z on 11-10, then recovered at 19:00Z. | Same as the row above. |

## Cetudy assertions 6 and 7: still no saturation window

Query `njAQxxhbUJg` (the spec of `eMctkLSc4hZ`), from 2026-11-11T01:00Z to
about 07:05Z. poweredge has been at 65–72 CPUs since about 04:00Z, with a peak
of 71.69. The longest streak at or above 70 is three 5-minute buckets
(06:10–06:20Z and 06:30–06:40Z). A qualifying window needs six. Over the same
span, datastore p99 stayed at about 0.015 s and k3s CPU pressure (some avg60)
peaked at 3.77.

## Consequence for the plan

1. Re-disposition `wFv7MbGL79` through its owner, as the two earlier "keep"
   rows were. Until then, assertion 3's 72-hour window can be graded only
   between weekly resets, and choosing a window just to avoid one would not
   honestly meet the assertion.
2. The five out-of-baseline groups each now have a measured disposition: real
   condition, no carrier, recheck at the final sweep.
3. Assertion 4 currently holds. Re-read it at the final sweep.
