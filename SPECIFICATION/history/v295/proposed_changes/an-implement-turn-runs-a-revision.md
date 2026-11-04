---
proposal: an-implement-turn-runs-a.md
decision: accept
revised_at: 2026-11-04T16:29:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed. legacy-coordinator-agent decided this under R301 (maintainer's factory-yield priority-1 direction, 2026-11-04 ~15:30Z) and relayed it to claude plan session e2fc325a, which selected it. The gate preview paragraph forbade the preview from SETTING a check-skip variable but said nothing about one it INHERITS, so a turn whose environment carries LIVESPEC_CHECK_SKIP would get a preview that passes on checks the commit node's hook then refuses. That is the late, budget-spending refusal the preview exists to prevent (measured 2026-11-04: 6 of 48 finished factory dispatches ended with the implement re-entry budget spent after hook refusals). This closes the gap that the spec-change-tier judgement on bd-ib-cwnt3b named at dispatch against spec v290. The new sentence adds to the existing prohibition without contradicting it, and the Scenario 285 case exercises it. No H2 heading changes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T16:29:57Z
verdict: NO BLOCKERS
proposal_stem: an-implement-turn-runs-a
content_digest: 6effdab0af58e514680e6e6814661b467381b8ba1385c9b5e8707db1dec3737d
