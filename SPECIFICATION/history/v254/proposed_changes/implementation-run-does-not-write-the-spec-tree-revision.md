---
proposal: implementation-run-does-not-write-the-spec-tree.md
decision: accept
revised_at: 2026-10-30T20:41:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise path (coordinator gitops-fleet-capacity-monitoring task, maintainer direction 2026-10-30: move pending proposals forward with AI-only consensus). Separate read-only Sonnet ratification review returned NO BLOCKERS. Adaptations to current text: The current paragraph already numbers Fourth, Fifth and Sixth (implement/review_fix rules), so the new rule is stated as a Seventh rule applying to implement, fix and review_fix, instead of 'MUST state four rules'/'Fourth'; the closing Scenario 202 sentence is reworded to cover it. The Scenario 202 sub-scenario is titled 'The stage prompts state the three rules and the spec-tree rule' instead of 'four rules' for the same numbering reason. The proposal's 'exactly as it refuses run-owned files under .github/workflows/' is kept verbatim, though the spec text does not itself state that refusal (the workflow implements it).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:09:17Z
verdict: NO BLOCKERS
proposal_stem: implementation-run-does-not-write-the-spec-tree
content_digest: 641d74a4af277e10a296c316ca8df6ff84ef42180e6e6f5ff1a97dcff4c158c6
