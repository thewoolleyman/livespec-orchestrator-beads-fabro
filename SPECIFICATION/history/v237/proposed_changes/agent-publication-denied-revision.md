---
proposal: agent-publication-denied.md
decision: accept
revised_at: 2026-10-27T00:19:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed under coordinator ruling R78 (high priority), on the maintainer's direction to make it impossible for a run's pull request to be merged partway through the run. A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) returned NO BLOCKERS on its fourth pass. Its earlier blockers were folded in: wrappers alone overclaim, so credential isolation and a broker are required; review findings go through the broker; and hooks and gates never hold the credential.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T00:13:54Z
verdict: NO BLOCKERS
proposal_stem: agent-publication-denied
content_digest: 9bc14db6feeb441cef95b395e435c4814919d7e3f2d37a8f6c3cf3625d0063c1
