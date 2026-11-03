---
proposal: dispatcher-fabro-rm-deletions-burst.md
decision: accept
revised_at: 2026-11-03T09:38:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Breakage mitigation for the 2026-11-03 store-lock storms on petri, whose 102 GB SQLite run store failed concurrent appends and interrupted seven live runs. No committed setting could defer or pace Dispatcher run deletions. The change extends the existing Sandbox retention and collection subsection, which the governing-heading judgement named, without changing retention, stop, retry or idempotence. The defaults defer collection while the factory runs anything and pace deletions 60 s apart host-wide. Turning deferral off with an interval of 0 restores today's behaviour exactly, so an operator can revert by config once the store fix bd-ib-h7kbco ships. Scenario 281 keeps its heading; its collection step is narrowed, and two scenarios exercise deferral and pacing. Re-cut as v283 on the merged v282 bytes, per legacy-coordinator-agent's revise order, and re-reviewed against the new digest. The resulting text differs from the proposal only in punctuation.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T09:38:20Z
verdict: NO BLOCKERS
proposal_stem: dispatcher-fabro-rm-deletions-burst
content_digest: 9c0712f180d988be13e4155b4c7bf1d553891553dcb8b29171c8b0ef167f06cf
