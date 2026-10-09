---
proposal: janitor-failed-target-attribution.md
decision: accept
revised_at: 2026-10-09T15:03:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: codex
---

## Decision and Rationale

This ratifies the existing plan assertion and bounded diagnostic child. It reuses private retention, permits only extracted target names beyond the bounded excerpt, and preserves normal failure disposition. No cited design record is contradicted. Independent read-only Sonnet review in native Claude session 7a138771-a3b0-4f8b-906b-9a039a0453c8 returned NO BLOCKERS for digest 76b1ac1245a74198e41139d88a094e43157200b3acc6246c84c251b162ac0738. The exact reviewed bytes are retained; the target-name exception is limited to outcome and journal metadata and does not authorize additional raw output or ledger/PR content.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-09T15:02:46Z
verdict: NO BLOCKERS
proposal_stem: janitor-failed-target-attribution
content_digest: 76b1ac1245a74198e41139d88a094e43157200b3acc6246c84c251b162ac0738
