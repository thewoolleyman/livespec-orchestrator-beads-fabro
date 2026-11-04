---
proposal: turn-waits-for-runner-commit.md
decision: accept
revised_at: 2026-10-27T14:10:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted, spec-first for bd-ib-xj3qqb and bd-ib-jzuryr (coordinator ruling R113, urgent). A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) raised two blockers in round 1 (the node-timeout carve-out and the overlapping refused-attempt definitions), both folded in. Round 2 and a ratification round after the proposal was filed each returned NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T13:21:04Z
verdict: NO BLOCKERS
proposal_stem: turn-waits-for-runner-commit
content_digest: 94f9451919418aff3989daa47a4aa2576d68c8872cbd61a02a07404c0ed34369
