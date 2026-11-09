---
proposal: a-merged-rework-re-dispatch-completes-through-reconciliation.md
decision: modify
revised_at: 2026-11-09T17:15:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

Accepted in substance under delegated decision mode, at the next free version after v335, in the slot legacy-coordinator-agent routed to this seat (shape decided under R301, 2026-11-09 about 12:4xZ). A merged rework re-dispatch whose merge wait was handed off rested active under rework:pending forever, because the survey and stranded-state clauses excluded every rework:pending item. Measured on bd-ib-ux2xee (run 01M6ZBZD1K3N, PR #4726, closed by hand with reconcile-merged --regrade). The revise defines a handed-off rework and a parked rework. It makes reconciliation's hold 8 completion of a handed-off rework's merged pull request its terminal disposition, moving it to acceptance and clearing rework:pending. It narrows the survey exclusion to parked reworks, and Selection never re-selects a handed-off rework. The independent read-only sonnet review first found ONE BLOCKER: the ratified reconcile-merged valve refusal of every rework:pending item, which the proposal's motivation wrongly called implementation-only, contradicted the new hold 8 sentence. A carve-out resolved it and the re-review found no blockers. Scenario 337 is added with a TODO coverage row and a debt-register row owned by bd-ib-if5luo.

## Modifications

Two changes beyond the proposal. (1) contracts.md §"Rework-pending re-dispatch" "Operator override": `dispatch --item` MUST accept an item carrying `rework:pending`, except a handed-off rework ("Selection" above). Without it, the proposal's new Selection sentence (dispatch --item refuses a handed-off rework, naming its pending pull request) contradicted that bullet. (2) contracts.md, the reconcile-merged valve's rework:pending refusal: it now excepts a handed-off rework whose own pull request merged, which §"Stranded claim release" hold 8 completes. The proposal's motivation called that refusal implementation-only, but it is ratified text, and without the exception it contradicts the new hold 8 sentence. Scenario 68 is unchanged: the item it refuses is a parked rework. Also, the new scenario is numbered 337, the next free number, and the proposal's bullet inserts are hard-wrapped to the surrounding 72-column style.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T17:14:57Z
verdict: NO BLOCKERS
proposal_stem: a-merged-rework-re-dispatch-completes-through-reconciliation
content_digest: 72711dc647ab55291f44fcab96943d9ff25d452abf7b6e7888d6cc04f95219b9
