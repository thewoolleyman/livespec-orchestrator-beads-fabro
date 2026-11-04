---
proposal: a-host-definition-of-done.md
decision: accept
revised_at: 2026-10-30T20:41:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise path (coordinator gitops-fleet-capacity-monitoring task, maintainer direction 2026-10-30: move pending proposals forward with AI-only consensus). Separate read-only Sonnet ratification review returned NO BLOCKERS. Adaptations to current text: The proposal anchors on the sentence in the pre-dispatch paragraph; the current spec states the no-verdict record rule in "Host judgements take the resolved dod_gate chain", so the did-not-run sizing is attached to that sentence (it covers both pre-admission and pre-dispatch, as the proposal intends). The new journal paragraph goes after "Judged again before dispatch" and before "Kept current". Note: a repository preflight is outside the input bound, so its row would carry only unreported/complete sizes; kept literal to the proposal. Scenarios are appended inside existing Scenario 239 as a scenarios.md edit (no new heading).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:09:04Z
verdict: NO BLOCKERS
proposal_stem: a-host-definition-of-done
content_digest: 695108b88b7e58821b6f643be7c6c9fed37321fc46a750b0364530b4b9ba17e5
