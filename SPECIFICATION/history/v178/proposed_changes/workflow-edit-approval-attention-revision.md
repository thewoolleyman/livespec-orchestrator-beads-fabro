---
proposal: workflow-edit-approval-attention.md
decision: accept
revised_at: 2026-10-21T04:43:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 10). Work-item bd-ib-qr4c7h records the maintainer's ruling of 2026-09-10 on livespec-dev-tooling-9ptz: the advisory workflow-edit control's notification mechanism is the approval:workflow-edit label surfaced in needs-attention, with no push automation, and no needs-attention gather read the label (measured 2026-09-11). The new fact follows the existing rules of 'Orchestrator-owned attention facts': a flat hygiene item per subject with its own id, summary and handoff, a work-item resource as the grammar permits, and a discuss-work-item handoff carrying the subject id, which is executable as advertised. No design record is contradicted. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes; its non-blocking notes (optional additional scenarios for label removal, store failure and coexistence) are left for a later amendment. Scenario 232 gains coverage and debt entries owned by bd-ib-qr4c7h.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T04:42:04Z
verdict: NO BLOCKERS
proposal_stem: workflow-edit-approval-attention
content_digest: d5f9852daaeb61fa3bf91f747aa525627dd7561bb05bc82adbd4d3984251ce77
