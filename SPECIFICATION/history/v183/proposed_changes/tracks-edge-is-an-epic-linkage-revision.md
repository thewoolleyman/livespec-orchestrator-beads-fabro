---
proposal: tracks-edge-is-an-epic-linkage.md
decision: modify
revised_at: 2026-10-21T13:24:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 2). Work-item bd-ib-rrhbmm: the plan child enumeration honours parent-child or tracks edges while the list-work-items projection computes parent from parent-child only, so the two surfaces would disagree silently once a tracks edge exists. The direction chosen keeps the already ratified plan child-enumeration union intact and generalizes the epic-linkage bullet to it. Modifications beyond the filed proposal: the rule also covers the plan-progress attribution of the no-result-window fact, and the epic-close check of the merge-evidence exemption, two surfaces that enumerated children by parent-child alone; Scenario 215 gains a second case for plan-progress attribution of a tracks-linked child closed inside the observation window. Scenario 215 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, found one blocker in round 1 (the attribution step did not establish a closure inside the window, which the governing paragraph requires); after the fix it returned NO BLOCKERS on the exact resulting bytes in round 2. Scenario 215 gains coverage and debt entries owned by bd-ib-rrhbmm. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md and touches no epic-linkage text.

## Modifications

contracts.md, section 'Work-item beads-issue mapping': the epic-linkage bullet names parent-child or a tracks dependency edge to the epic, and requires every surface that reports a parent or enumerates an epic's children (the plan child-enumeration union, the context children, the list-work-items --json parent, the plan-progress attribution and the epic-close check) to honour both. Section 'context': the children union names every epic-linkage edge. Section 'Attention without confusing activity with results': plan-progress attribution uses every epic-linkage edge plus dotted-id children. The merge-evidence exemption's epic-close check counts epic-linkage members. scenarios.md: Scenario 215, 'A tracks edge links a record to its epic on every surface', with a child-on-every-surface case and an in-window plan-progress attribution case.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T13:23:50Z
verdict: NO BLOCKERS
proposal_stem: tracks-edge-is-an-epic-linkage
content_digest: e9231e43ce3d47db6c6b56e0fbe2f97da88c6fab9c7ebef0aa917c47fb811852
