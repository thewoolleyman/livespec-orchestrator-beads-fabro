---
proposal: proof-loop-graph-change.md
decision: modify
revised_at: 2026-10-20T23:37:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fabro-currency (session f2f0c4ef)
---

## Decision and Rationale

Ratified by consensus panel 2 (coordinator R350, 3-of-3) under the maintainer's 2026-10-20T21:52:55Z authorization, which sends doubtful items to a consensus panel and acts on its majority. The credential part was ratified with required changes (a)-(f), all folded into the proposal before this revise; the refresh rule was ratified as worded. Departure from a design record, named deliberately: bd-ib-yx7pdm (maintainer-approved 2026-10-05) defined the freshness requirement as the workflow-resolved execution allowance plus the margin. This revision makes the requirement the smaller of that allowance and a bounded credential-use window, because the whole-run wall budget (bd-ib-sdxfsn, 2026-10-14) and the deadline-killing in-sandbox guard now exist; the panel weighed and accepted that departure. Measurements: plan/fabro-currency/research/013-credential-requirement-and-refresh-carry-forward-2026-10-20.md.

## Modifications

Folded the independent ratification reviewer's four round-1 blockers verbatim: (1) the Worker credential projection implementation-ownership paragraph no longer leaves the numeric threshold implementation-owned, only the margin, and cites Scenario 228; (2) the resume anchor list gains the credential-use-deadline-reached record, with the same published-head, stage and proof-record-precedence restrictions, and Scenario 228's unmeasured-budget case gains its prerequisites; (3) Scenario 229's positive case keeps every deterministic carry-forward check, and Scenario 178 is renamed to 'A refresh carries verified proof forward only when the deterministic carry-forward conditions hold' (coverage row renamed in the same commit); (4) Scenario 228 gains invalid-queue, execution-allowance reporting, independent credential-life and later-launch cases, the margin step, and the full disposition assertions in each cause case. Round 2 returned NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T23:36:26Z
verdict: NO BLOCKERS
proposal_stem: proof-loop-graph-change
content_digest: 21fe5a7e56b2e9bfb161a0aee1d6aec92decaebb081815ee23be7f24325ee98c
