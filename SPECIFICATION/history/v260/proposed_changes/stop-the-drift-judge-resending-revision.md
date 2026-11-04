---
proposal: stop-the-drift-judge-resending.md
decision: modify
revised_at: 2026-10-31T18:37:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:split-drift-check-from-cleanup-timer
---

## Decision and Rationale

Modified, then accepted. The proposal generalizes §"The skill surface" → "The drift run." with prompt batching. A drift-job run renders the ratified spec tree into one judge prompt for all the merges it judges, never once per merge. It splits across the fewest prompts that fit only when the content exceeds the judgement's input limit, and its --json outcome reports the prompt count. Filing and finding identity are unchanged. This is the second of the two token-waste fixes the maintainer's 2026-10-25 ruling requires before the split-out drift job may be enabled (plan split-drift-check-from-cleanup-timer, work-item bd-ib-wqciv7). The reviewer's first pass blocked on the over-limit split having no scenario; the added scenario resolves it, and the second pass returned NO BLOCKERS on these exact bytes. No design record is contradicted. Ratified with --only-topic: the pending proposal label-every-host-model-judgement belongs to another thread.

## Modifications

Added a second Scenario 207 case, "Merges whose content exceeds the input limit are split across the fewest prompts that fit", so the over-limit split and the reported prompt count carry a scenario as well as a clause. This addresses the independent ratification reviewer's one blocker. The contracts.md text is unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-31T18:36:59Z
verdict: NO BLOCKERS
proposal_stem: stop-the-drift-judge-resending
content_digest: ea03aae6be5a159ec6815089de1e7105d37f3a8909d5e90304c02c4a0ec8fc5a
