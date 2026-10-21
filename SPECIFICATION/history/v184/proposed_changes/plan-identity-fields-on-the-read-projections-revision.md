---
proposal: plan-identity-fields-on-the-read-projections.md
decision: modify
revised_at: 2026-10-21T13:44:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 2). Work-item bd-ib-wi5b: the list-work-items --json view drops a plan epic's plan_slug, next_action and last_session, and the context envelope carries next_action without last_session, so a consumer that reads only these surfaces (the console's Plans roster) cannot render a plan record. The revise publishes the three keys on epic records of the list-work-items view, null on every other record, and adds last_session to the context envelope; both are read-only projections of metadata the plan primitives already write. Modification beyond the filed proposal: the sentence stating that only lane and lane_reason are computed additions is reworded so it stays true beside three metadata-read keys. Scenario 216 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes. Scenario 216 gains coverage and debt entries owned by bd-ib-wi5b. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'list-work-items': the computed-additions sentence is reworded, and a new sentence requires each epic record to carry plan_slug, next_action (the typed object exactly as stored, or null) and last_session read from the epic's metadata, with null for all three on every other record. Section 'context': the envelope carries last_session beside the typed next_action. scenarios.md: Scenario 216, 'The read projections publish a plan epic's identity keys', with an epic-and-non-epic list case and a context case.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T13:44:00Z
verdict: NO BLOCKERS
proposal_stem: plan-identity-fields-on-the-read-projections
content_digest: 08d70a7dae096c1a392888450ea74f56cdfe39509b6a7a4bbbe1d1097c04682c
