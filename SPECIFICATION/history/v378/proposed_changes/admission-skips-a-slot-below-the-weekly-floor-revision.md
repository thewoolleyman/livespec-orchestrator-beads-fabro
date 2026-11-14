---
proposal: admission-skips-a-slot-below-the-weekly-floor.md
decision: accept
revised_at: 2026-11-14T17:01:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded the proposal PASS-WITH-FIXES at 3f9730fad and then PASS at 1bd18ba1b (PR #5290, merged 2026-11-14T15:56:28Z as b57ce4cc1). On 2026-11-14 it placed this revise next in the orchestrator queue after v377 (every-commit-refusal-re-entry), as the root fix for that day's factory credential pause; the proposal releases bd-ib-eogs2t. Session-headroom admission now also refuses to qualify a Claude pool slot whose valid seven-day remaining headroom is strictly below the committed-only dispatcher.session_headroom_weekly_floor_percent (default 10, matching the caam rotation loop's weekly reserve). That skip is journaled as a seven-day floor skip, distinct from the seven-day skip, and it removes slots without changing the ranking. Measured gap: at 2026-11-14T14:44:33Z admission chose ANTHROPIC_1 at 99 percent seven-day utilization (status allowed_warning, five-hour window absent), and livespec-57r6qo's run 01M7D8AHQKYT died at proof_capture on the weekly limit. Accepted as written; the independent review found no blockers.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T17:00:13Z
verdict: NO BLOCKERS
proposal_stem: admission-skips-a-slot-below-the-weekly-floor
content_digest: aef11507830e1818d166914a16b93683b6a123279764c40acbf730a9feb76763
