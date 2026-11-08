---
proposal: fix-turn-commits-run-the-affected-tests-gate.md
decision: accept
revised_at: 2026-11-08T02:43:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session a21903eb, claude-opus-5-5) under R301 delegated authority on 2026-11-08: ACCEPT on content digest b571a588, after reading the 222-line diff against 28c024663. A fix turn's commits now take the affected-tests gate like implement and review_fix commits, and a fix turn grades each tree once through its commit hook; the janitor still runs the full check aggregate once on the pushed tree, so no merged tree is graded less. A workflow.fabro change is a scoped change that runs the tests reading the graph. Basis: in this repository a full aggregate in a fix turn's commit hook outlasted the 3600 s fix limit twice on 2026-11-07 (3654.8 s, 3765 s for its coverage leg alone). Carried in the same pass as janitor-refresh-merge-grades-once.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T02:40:59Z
verdict: NO BLOCKERS
proposal_stem: fix-turn-commits-run-the-affected-tests-gate
content_digest: b571a5883c33712456365dece1fd032decef46113f291dabed3ee946b34adda1
