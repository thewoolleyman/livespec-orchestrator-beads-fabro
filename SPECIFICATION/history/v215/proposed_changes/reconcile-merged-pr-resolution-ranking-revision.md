---
proposal: reconcile-merged-pr-resolution-ranking.md
decision: accept
revised_at: 2026-10-25T04:00:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies bd-ib-ob26ab, stability tier, under coordinator gitops-fleet-capacity-monitoring's maintainer-directed commission. Merged-PR resolution ranks head ref, then title, then body mention, and refuses only on a tie in the highest non-empty tier. Re-cut onto master after a version collision. The independent read-only review over the exact re-cut bytes (gpt-6-astra, session 01a17136-153c-7773-a150-4ca50b06fc7d) returned NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T03:59:57Z
verdict: NO BLOCKERS
proposal_stem: reconcile-merged-pr-resolution-ranking
content_digest: 73b50079cddce58b5aa0a99afca1d8f74c5ef1c7653bc8fedf266b5840976dc4
