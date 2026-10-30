---
proposal: factory-credential-from-whole-slot-pool.md
decision: accept
revised_at: 2026-10-30T21:24:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise path (coordinator gitops-fleet-capacity-monitoring task, maintainer direction 2026-10-30: move pending proposals forward with AI-only consensus). Separate read-only Sonnet ratification review returned NO BLOCKERS. Adaptations to current text: Where a slot's projection is unavailable, the existing fail-open rule is kept (the slot still qualifies, since the floor governs it), but it ranks below any qualifying slot whose projection was measured or carried, so a slot with evidence is preferred to one without. Two additions beyond the brief: a slot whose response carries no reset instant ranks after slots that carry one, with ties broken by slot name ascending for determinism; and the 'one bounded reading' sentence and the refusal-record bullet are widened to one reading per pool slot. The paragraph that advised aligning the caam rotation trigger with the floor is replaced, since the band it described can no longer idle the factory. The unnumbered CLAUDE_CODE_OAUTH_TOKEN is the sole pool slot only when no numbered slot is injected. The Codex clause is untouched. Phrases in the existing headroom scenarios such as 'the primary credential' refer to the primary candidate's credential and stay true with a one-slot pool, so they are not edited. Review fixes: the Definition-of-Done judge credential rule now takes the pool slot; floor-0 qualification; passage moved for antecedent; single-slot pool steps added to six Scenario 60 group scenarios.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T21:24:48Z
verdict: NO BLOCKERS
proposal_stem: factory-credential-from-whole-slot-pool
content_digest: b16ab6524657c2e1b84e8287458d212f7bfff103673a65d8fbb7cc94658d5ee9
