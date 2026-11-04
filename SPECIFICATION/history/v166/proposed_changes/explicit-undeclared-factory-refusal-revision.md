---
proposal: explicit-undeclared-factory-refusal.md
decision: modify
revised_at: 2026-10-20T01:32:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted per coordinator ruling R264(B): an explicit factory selection (--factory or a set, non-empty LIVESPEC_FABRO_FACTORY) naming an undeclared factory silently misrouted run 01M5BAYK2NNZ to the local Fabro server. Generalizing the existing before-claim registry refusal closes that gap without a new clause.

## Modifications

One wording tightening in contracts.md: 'It MUST refuse the same way a dispatch whose ...' becomes 'It MUST equally refuse a dispatch whose ...', removing the reading in which 'the same way' attaches to the dispatch rather than to the refusal. No other change to the proposal's diff.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T01:31:49Z
verdict: NO BLOCKERS
proposal_stem: explicit-undeclared-factory-refusal
content_digest: 7f7bbc74f5cae94788e532f83da7dd26dbf3f79dd9cb4cbeb56e9e5b316fe044
