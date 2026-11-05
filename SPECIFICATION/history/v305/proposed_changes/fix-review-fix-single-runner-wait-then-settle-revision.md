---
proposal: fix-review-fix-single-runner-wait-then-settle.md
decision: accept
revised_at: 2026-11-05T12:44:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent, which ruled ACCEPT AS PROPOSED in advance under R301 (2026-11-05 ~12:20Z). The revise was run by plan seat implement-test-performance (epic livespec-dev-tooling-sv6m5p). Measured: a fix turn of bd-ib-s5idxj run 01M6N40ME98DE6TDZKSQ3G377P polled one runner commit about 45 times over 46 minutes and ended on its 3600 s turn timeout, despite bd-ib-oueyxf's prompt rule. The stage's commit-run settle (fix_commit_settle / review_fix_commit_settle) already waits on every commit run left running before the stage outcome is decided, so repeated in-turn waits buy only a timeout. This makes the one-wait limit mechanical: the runner refuses a second wait from the same stage visit. No other ratified statement conflicts, and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T12:43:50Z
verdict: NO BLOCKERS
proposal_stem: fix-review-fix-single-runner-wait-then-settle
content_digest: 03de8e2011a813c3df13ec91715e24fd5b3fcc0e1f56125826a8cba6ae0d8709
