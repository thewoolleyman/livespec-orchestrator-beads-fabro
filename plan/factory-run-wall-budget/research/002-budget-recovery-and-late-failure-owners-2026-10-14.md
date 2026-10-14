# What the budget recovers, and who owns each late failure (2026-10-14)

Written 2026-10-14 by the factory-run-wall-budget plan session in answer to the coordinator
(gitops-fleet-capacity). The coordinator pointed out that a 21600-second budget recovers little of
the slot time this plan exists to recover, and asked the plan to carry the fail-early half of
bd-ib-sdxfsn or record why not, and to state what the shipped change is expected to recover.

## What the budget is expected to recover

The budget is a BACKSTOP, not the throughput fix.

- Coordinator's figure for the 2026-10-13 cap-10 window: only 2 needs-human runs exceeded 360
  minutes (bd-ib-nfbyot 390, bd-ib-6jkjzm 394), so a 21600-second budget would have freed about
  1 slot-hour of the roughly 48 that were held.
- This session's figure for 2026-10-07 to 2026-10-14 (note 001): about 7 slot-hours a week.
- The table below gives the same answer: 7.0 of 250.5 slot-hours (2.8%).

Why the default stays at 21600 seconds: the longest success in the window is bd-ib-zi5ygh at 348
minutes. A lower default would cut off measured healthy runs, which the maintainer's outcome ("get
done correctly") rules out. What the budget guarantees is a CEILING: no run holds a slot for 7 to 9
hours again (the 481-, 506- and 548-minute runs). It does not shorten the 200-to-360-minute parks.

## What makes long runs fail late: measured on hp

Source: `fabro ps -a --server https://hp-xubuntu.perch-rudd.ts.net:32276 --json` and one `fabro
inspect --json` per run, read 2026-10-14 01:10Z-01:20Z. The population is every `ImplementWorkItem`
run that started on or after 2026-10-07, ended `failed` and ran longer than 180 minutes: 58 runs,
250.5 slot-hours, across every fleet repository dispatching to hp.

Each run is classified by the last element of the cause chain of its last failed non-needs_human
node. When no node failed, the run's `conclusion.failure.detail` is used instead.

"Beyond 6 h" is the part of the wall time the 21600-second budget would have returned.

| Class | Runs | Slot-hours | Beyond 6 h | Owner (live) |
|---|---|---|---|---|
| publish_draft script failed: sandbox push hooks (for example `livespec_dev_tooling is not importable`), an expired GitHub App token (HTTP 401), exit 128, or a 1800 s timeout | 11 | 53.8 | 4.2 | plan publish-draft-green-work-loss (bd-ib-acrr56; bd-ib-xi63mq active); bd-ib-s22sg (401 token) under plan stall-watchdog-false-kills (bd-ib-laf735) |
| Engine checkpoint commit failed or timed out (the repository pre-commit aggregate runs inside each checkpoint) | 11 | 44.6 | 0.0 | plan checkpoint-commit-hook-failures (bd-ib-hcwmnq; bd-ib-jb53pu in acceptance, bd-ib-6jkjzm active) |
| Provider session limit hit mid-run ("You've hit your session limit · resets …") at implement, fix or proof_capture | 11 | 42.5 | 0.0 | No item-level owner. Provider-limit release (v127) governs the item afterwards; see the deferral below |
| ACP turn timed out at the node's own timeout (implement, proof_capture, pr, fix, review_fix) | 6 | 35.1 | 2.8 | Per-node timeouts (bd-ib-cnkf, closed); this repository sets implement 14400 s |
| Review/disposition loop reached its visit cap, failing as an engine cycle error | 5 | 20.8 | 0.0 | bd-ib-3xdhc6 under plan hp-factory-failure-follow-ups (bd-ib-qieqc6) |
| pr stage: push/rebase failure, or a tool call moved to the background | 4 | 13.9 | 0.0 | plan pr-stage-backgrounded-push-fault; bd-ib-c3txja (scripted refresh, in acceptance) |
| janitor deterministic failure or failure cycle | 3 | 11.7 | 0.0 | Item-specific (spec slug format) |
| Other single cases (uncapturable proof assertions, ACP internal errors, cancelled) | 7 | 28.1 | 0.0 | Item-specific |
| **Total** | **58** | **250.5** | **7.0** | |

## Why this plan does not carry the fail-early half

The fail-early half is not one mechanism. It is one fix per failure class, and every class that
fails at a check has a live owner already working it. The two largest classes are both checks run
inside the sandbox late in the graph — push hooks at publish_draft, and pre-commit at each engine
checkpoint — and both have active items in their own plans. The fix those plans make is exactly
the fail-early fix: stop running the long aggregate where it fails late, or fix the environment it
fails in. Filing a parallel "move the check earlier" item here would put a second owner on the same
defect.

So this plan carries the backstop. It also maps every class to its owner (above), so the
coordinator can see whether the owners are moving. The assertion-2 measurement window of this plan
re-takes this table after release, which shows whether the classes are shrinking.

## Deferral: provider session limit hit mid-run

This is the one large class with no item-level owner: 11 runs, 42.5 slot-hours. It is not a late
CHECK. It is a capacity event: the account's rolling session window ran out hours into the run. So
no check can be moved earlier.

The fail-early form would be an admission-time headroom test: do not start a multi-hour run on an
account whose session window is nearly spent. That belongs with the provider-limit and
account-rotation owners, not with a slot budget:

- The Dispatcher's provider-limit release and fallback chain (plan
  factory-configurable-model-fallback-priority).
- Account rotation (livespec-overseer `caam-anthropic-loop`).

Reported to the coordinator for routing on 2026-10-14. Reconsidered in this plan only if the
assertion-2 window shows budget cancels dominated by this class.
