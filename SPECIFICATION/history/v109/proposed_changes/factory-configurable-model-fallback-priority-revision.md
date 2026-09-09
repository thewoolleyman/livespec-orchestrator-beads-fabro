---
proposal: factory-configurable-model-fallback-priority.md
decision: accept
revised_at: 2026-09-09T13:23:54Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: codex-gpt-5
---

## Decision and Rationale

Accept the rebased and independently critiqued provider-generic per-node fallback contract: it preserves v108/v107 primary resolution, migrates legacy containment without contradiction, makes retry/side-effect/event/cost behavior explicit, and adds scenario plus heading coverage atomically.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-09T13:22:34Z
verdict: NO BLOCKERS
proposal_stem: factory-configurable-model-fallback-priority
content_digest: b4eca527bf5ea72fd2f5a3eb654f5d03bd6c2f8ab475a94590b270adcd151593
