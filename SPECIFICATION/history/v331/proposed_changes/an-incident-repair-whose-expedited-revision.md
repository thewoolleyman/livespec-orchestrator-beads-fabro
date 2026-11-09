---
proposal: an-incident-repair-whose-expedited.md
decision: accept
revised_at: 2026-11-09T09:08:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as filed. The ratified lifecycle admits a corrected repair only from collecting-failures, so a repair whose pr-bound expedited PR fails a retained fast check before merge has no successor (measured on livespec-dev-tooling-e62ss6 attempt 3, PR livespec-dev-tooling#3828, run 42520940297). The amendment appends a corrected repair successor without rewriting the bound carrier, gates it on forge facts (PR closed unmerged at the carrier head and ref; the named run completed with conclusion failure on that head), retains the failed run with the item's failures and keeps the unchanged-reland rule. No H2 heading changes. Independent sonnet ratification review: NO BLOCKERS at 2026-11-09T07:52:22Z, re-confirmed at 2026-11-09T08:27:20Z over these exact bytes rebuilt on v330; its doctor-style walk mapped every MUST to an enforcing code path in the bd-ib-elq5ry implementation draft.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T08:27:20Z
verdict: NO BLOCKERS
proposal_stem: an-incident-repair-whose-expedited
content_digest: 3922a9c49d2ba6bfa0965c0f04a354ffee8c0ae4f2570a03c38ecc805fdcd684
