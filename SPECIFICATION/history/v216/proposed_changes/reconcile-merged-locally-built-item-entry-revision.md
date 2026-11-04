---
proposal: reconcile-merged-locally-built-item-entry.md
decision: modify
revised_at: 2026-10-25T04:01:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies bd-ib-acxptq, stability tier, under coordinator gitops-fleet-capacity-monitoring's maintainer-directed commission. reconcile-merged accepts a merged, locally built item resting at pending-approval or plain ready, identified by head ref or title only, with the same janitor and acceptance path and the resting status in place of active. An earlier review (session 01a17117-e6cb-7332-ba50-81174908dc7a) found one blocker, now fixed. The final independent review over the exact re-cut bytes (gpt-6-astra, session 01a17136-0258-7580-9b4b-ed25ecd90cf4) returned NO BLOCKERS.

## Modifications

The body-only refusal scenario establishes an explicit merged pull request that mentions the id only in its body, and a locally built item without recovery routing.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T03:59:34Z
verdict: NO BLOCKERS
proposal_stem: reconcile-merged-locally-built-item-entry
content_digest: 34a37c1ba7f30bc19d74f1caec2d754708d3a8639c86e8caa045ef516e2caa29
