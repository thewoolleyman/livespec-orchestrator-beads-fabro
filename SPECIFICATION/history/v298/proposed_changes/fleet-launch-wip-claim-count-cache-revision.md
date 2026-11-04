---
proposal: fleet-launch-wip-claim-count-cache.md
decision: modify
revised_at: 2026-11-04T19:45:36Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Decided in delegated mode by claude:gmktec-factory-placement under legacy-coordinator-agent ruling R301, as the repair step 2 the bd-ib-zwtfbq SCREEN REPAIR PLAN (2026-11-04T15:58Z) names. It states, under §"Provisional fleet launch scripts", the shared per-repository WIP claim-count cache the committed fleet-launch launchers MUST carry, so the bd-ib-x7bwug cutover does not bring back the ~29-process per-poll WIP load measured on 2026-11-04 (VPS CPU PSI 71-82). It builds on v296's repository WIP gate (bd-ib-3ufx6l) and adds no admission authority: the counted-claims count stays the projection's value and the Dispatcher's WIP cap remains the sole admission authority.

## Modifications

Three changes against the proposal text. First, the first independent review found two blockers. (1) Defining the gate's count as projection plus in-flight read as a redefinition of the counted-claims count and as a second capacity source: the bullet now defines an in-flight addition (fleet in-flight markers whose launcher process is still running, for not-yet-active items, excluding the launcher's own) that refines the comparison of the repository WIP gate and the breakage exception, and states it is a launcher-side early-yield margin only, the counted-claims count staying the projection's value and the Dispatcher's cap the sole admission authority. (2) A failed recomputation had no path: a failed recomputation or an unobtainable serialization is now an unreadable count under the WIP gate's rule (no hold, no cache file written), with a harness clause and a scenario case. Second, the scenario is numbered 309, not 308, because v297 (PR #4397) took Scenario 308 while this pass waited; its cases now also cover the failed recomputation and compare sums rather than counts. Third, the heading-coverage TODO row and debt-register entry for Scenario 309 (integration tier, owned by bd-ib-zwtfbq) are co-edited in the revise commit. The re-review of the final rebased bytes found NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T19:44:57Z
verdict: NO BLOCKERS
proposal_stem: fleet-launch-wip-claim-count-cache
content_digest: 1d9185cced0d82dbd111584243f7647161293f033ec8fc9d751655404bf5d202
