---
proposal: held-items-bounded-ledger-reads.md
decision: accept
revised_at: 2026-10-27T15:21:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted, spec-first for bd-ib-hm4obe (host-load reduction routed by petri-factory-on-gmktec under coordinator ruling R127; the dispatcher's pre-dispatch judgement refused it at 13:42Z because no clause governed this read shape). A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) reviewed the filed proposal with its edits applied and returned NO BLOCKERS at 2026-10-27T14:16:41Z. needs-attention's held-items listing reads the ledger a bounded number of times per snapshot rather than once per heldable item.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T14:16:41Z
verdict: NO BLOCKERS
proposal_stem: held-items-bounded-ledger-reads
content_digest: 4e35964d1a136c988169491ef6dbb87b2c0fe8ed94cccf8db27e3379edb0ba3d
