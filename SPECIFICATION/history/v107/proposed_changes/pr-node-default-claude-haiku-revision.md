---
proposal: pr-node-default-claude-haiku.md
decision: accept
revised_at: 2026-09-09T09:14:02Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Move the pr/publish ACP node's built-in fleet default off the dead Codex slug gpt-5.4-mini to a model-agnostic Claude Haiku 4.5 adapter, mirroring the implementer class's Claude default; pr expands to Codex only on an explicit dispatcher.codex_models.pr table. Human confirmed the Haiku default; an independent read-only Sonnet reviewer ratified the exact contracts.md + scenarios.md bytes with NO BLOCKERS after a first pass caught and I fixed a scenarios.md co-update omission.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-09T09:13:12Z
verdict: NO BLOCKERS
proposal_stem: pr-node-default-claude-haiku
content_digest: 5e5786e63e942ef86fb4cff963ea8a4c945f0949ae01ec7a0e5a823e85161dba
