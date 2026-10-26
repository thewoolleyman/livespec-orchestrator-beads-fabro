---
proposal: sandbox-test-parallelism-four.md
decision: accept
revised_at: 2026-10-26T10:34:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Fleet coordinator ruling R25, 2026-10-26: a measured four-worker per-file-coverage gate peaked at 2748 MiB of cgroup memory, 36% of the factory sandbox's 7630 MiB and inside the 6100 MiB bar, so the projected test-worker value moves from 2 to the sandbox CPU limit of 4. The clause's CPU-limit rule is unchanged; the constant and its tests land through a factory work-item.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T10:34:47Z
verdict: NO BLOCKERS
proposal_stem: sandbox-test-parallelism-four
content_digest: 6c85fb8646aeaeebf560d28fe5314bb14cd81aaad0e7d0b77b106b89bade2bb2
