---
proposal: judge-each-default-branch-merge.md
decision: accept
revised_at: 2026-10-31T18:35:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:split-drift-check-from-cleanup-timer
---

## Decision and Rationale

Accepted as filed. It generalizes §"The skill surface" → "The drift run.", the clause the spec-change tier classifier names for drift-job behaviour, with verdict reuse: a drift-job run invokes no model judgement for a merge already judged against the same ratified spec revision, re-judges it only once a newer revision exists, and a held or failed finding that stops the frontier does not re-judge the merges behind it. This is the first of the two token-waste fixes the maintainer's 2026-10-25 ruling requires before the split-out drift job may be enabled (plan split-drift-check-from-cleanup-timer, work-item bd-ib-qupk5g). It is consistent with the frontier rule and the retried-pass-files-no-duplicate rule: a merge whose pass failed has no recorded verdict and is still judged. Scenario 207 gains the matching scenario; no H2 heading changes. No design record is contradicted. Ratified with --only-topic: the pending proposal label-every-host-model-judgement belongs to another thread and is left in place.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-31T18:34:04Z
verdict: NO BLOCKERS
proposal_stem: judge-each-default-branch-merge
content_digest: 0a44315d4974f8fff9774ebe95e1ed43274e659b7d7a042309a21d53f0f80043
