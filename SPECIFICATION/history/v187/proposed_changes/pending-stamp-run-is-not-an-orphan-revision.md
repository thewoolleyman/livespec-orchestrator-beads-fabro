---
proposal: pending-stamp-run-is-not-an-orphan.md
decision: modify
revised_at: 2026-10-21T14:59:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 5). Work-items bd-ib-m1av and bd-ib-cewr.5: the claim half of a re-dispatch was protected by the pending stamp of "Stranded claim release", but the run half was not, so a just-launched run whose own stamp had not landed read as superseded by its item's previous journaled run, and a sibling reconcile pass cancelled it (measured 2026-09-06 in livespec-dev-tooling on run 01M1VPM6S3DC, 18 seconds old, and 2026-09-08 in the console tenant on three fresh runs). While an item's claim carries a pending stamp, a non-terminal run attributed to it is not an orphan. Modification beyond the filed proposal: Scenario 104's "An item superseded by a newer dispatch" case required cancelling exactly such a run, so it gains the premise that the item's claim carries a run stamp naming the second run, not a pending stamp; Scenario 223's second case premises an active claim whose run stamp names run B. The reviewer noted, and this revise does not change, that a dispatch dying after creating its run but before stamping it is held as attribution-pending with the operator move valve as the remedy, per the ratified "Stranded claim release". Scenario 223 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, found the Scenario 104 conflict as the one blocker in round 1, and after the fix returned NO BLOCKERS on the exact resulting bytes in round 2. Scenario 223 gains coverage and debt entries owned by bd-ib-m1av. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'A factory run never awaits a human', run-reconciliation bullet: after the ORPHAN definition, the filed sentence that a non-terminal run attributed to an item whose claim carries a pending stamp MUST NOT be classified an orphan. scenarios.md: Scenario 104's superseded case gains the premise that the item's claim carries a run stamp naming the second run, not a pending stamp; Scenario 223, 'A run attributed to an item under a pending stamp is not an orphan', whose second case premises an active claim whose run stamp names run B.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T14:59:09Z
verdict: NO BLOCKERS
proposal_stem: pending-stamp-run-is-not-an-orphan
content_digest: ac9f67edb1f5bbe9f249746c9095d19850434bc302085fe30d5c2d4a1491dfda
