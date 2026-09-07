# 003 — The backlog sweep widened this epic's child set from six to ten, and closed the deferral home note 001 named

Research note for plan thread `fabro-fork-control-plane-gaps` (epic
`bd-ib-bb41`), 2026-09-06, same session as 001 and 002. Status is read from
the ledger, never from this file.

## What happened (measured 2026-09-06 through `bd show` and `bd comments`)

Between this thread's first scope event (07:18 UTC) and its first handoff
(07:47 UTC), the maintainer-directed backlog sweep session (`bd-ib-j81s`,
verdict table in `plan/orchestrator-backlog-sweep-for-console-control-plane/research/001-verdict-table.md`,
PR #2186) re-parented four items under this epic at 07:24 with verdict KEEP,
and closed `bd-ib-6qu` (the 0.254 to 0.290 migration item) as a permanently
poisoned record. Note 001 §4 and the first scope event therefore describe a
six-child epic that is now a ten-child epic, plus this thread's own
`bd-ib-7hta4l`. The second scope event on the epic carries the binding
amendment (R8 to R11, D1 corrected); this note is the readable account.

| Re-parented item | Was | Status | What it is | Route |
|---|---|---|---|---|
| `bd-ib-i523` | standalone | `ready` P1 | a long-lived sandbox OOM-kills the engine's own checkpoint commit, discarding a green result (run `01M04JY6D569NQ6PR7WSPQ3GQ2`); implementer chooses memory recycling, a higher limit for gate-heavy repos, or resume from the agent's last local commit | fork-side, factory-ineligible; checkpoint-adjacent to .5 |
| `bd-ib-js4t57` | standalone | `ready` P2 | hook-refused pre-clone push silently falls back to a synthetic snapshot base; fail staging loudly instead (engine half of `bd-ib-pums`) | fork-side, already labelled `factory-safety:fork-upstream`; factory-ineligible |
| `bd-ib-jm4efv` | standalone | `ready` P2 | checkpoint-budget expiry classified `transient_infra` by generic timeout substring in the fabro failure classifier; targets `thewoolleyman/fabro`, canonical destination `fabro-sh/fabro` | fork-side, factory-ineligible; small, Wave A candidate |
| `bd-ib-i3zhgk` | child of `bd-ib-6qu` | `blocked` needs-human | run the Enemy Unit Test suite against a candidate fabro build and record the delta; its two blockers (`bd-ib-62xaj3`, `bd-ib-5g3voe`) are closed | human-gated operator run; the instrument for the forward-port deferral |

All four now carry a `ROUTE` comment (the three fork items also carry
`factory-ineligible`); `bd-ib-i3zhgk` was left unlabelled because it is an
operator run, not a build.

## The correction this forces on 001 and 002

Note 001 §2 and the first scope event's D1 said forward-porting to a base at
or above 0.290 is "reconsidered in `bd-ib-6qu`". That item closed today, so
the deferral had no live home for about half an hour. D1 is re-homed HERE:
the base ceiling below 0.256 still stands (ratified constraint), and
`bd-ib-i3zhgk` is now the instrument that would make a candidate build
decidable. The `workflow.fabro` migration for fabro #474 would be refiled
under this epic if and when a candidate passes. D2 (ACP user-input requests)
follows D1.

## Effect on the proposed waves (still a proposal)

- Wave A gains `bd-ib-jm4efv` (a classifier change with its own Red test
  criteria), alongside .2, .5, .3 and the .1 fork half. Still one rebuild.
- Wave B gains `bd-ib-js4t57` alongside .4 and .6.
- `bd-ib-i523` needs a design choice among its three directions before it is
  wave-placed; it shares `sandbox_git.rs` with .5, so placing it in Wave B
  after .5 lands avoids two edits to the same seam in one PR.
- `bd-ib-i3zhgk` is not a wave: it is an operator run against a candidate
  build, and nothing in Waves A or B depends on it.

The typed next action on the epic is unchanged: dispatch `bd-ib-7hta4l`, then
start Wave A operator-side.
