---
proposal: adapter-launch-release.md
decision: accept
revised_at: 2026-10-14T06:37:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-factory-configurable-model-fallback-priority
---

## Decision and Rationale

Implements the remedy bd-ib-x3la32 asks for within the ratified fallback model: a hold-free release of the first consecutive ACP adapter launch failure, keeping the ruling that a pre-turn failure is not provider evidence. An independent Codex gpt-6-astra review returned two blockers (disjointness from the availability route; a conservative, observable prompt-boundary rule), both folded in with its wording, and its second pass returned NO BLOCKERS on these exact bytes. Its non-blocking note that an ordinary code-0 pre-protocol exit is now included is accepted deliberately; its fixture suggestions are carried into bd-ib-x3la32's Definition of Done.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-14T06:36:59Z
verdict: NO BLOCKERS
proposal_stem: adapter-launch-release
content_digest: 81647432871473785ffde24673ba930ae6ee87ceccff2965d55d4a25aa3acab2
