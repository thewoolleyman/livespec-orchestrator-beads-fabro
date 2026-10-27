---
proposal: pr-refresh-rejected-push-that-landed-on-origin.md
decision: accept
revised_at: 2026-10-27T05:22:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed, spec-first for bd-ib-bu553k (pr_refresh reports a rejected push that landed on origin as a lease failure). The filed proposal came from the plan's capture-spec-drift pass. It also supplies the rejected-push cause that Scenario 248's absent-branch case already refers to. A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) returned NO BLOCKERS in its first round, and found it consistent with v243's own-checkpoint rule and with refresh repair.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T04:49:45Z
verdict: NO BLOCKERS
proposal_stem: pr-refresh-rejected-push-that-landed-on-origin
content_digest: 62e0902359a687a10be35b7fe1dc55a897d0b01c2ee50afc46ea32e3ec3c2798
