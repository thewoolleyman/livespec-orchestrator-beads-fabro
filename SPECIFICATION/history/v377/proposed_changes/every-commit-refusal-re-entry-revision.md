---
proposal: every-commit-refusal-re-entry.md
decision: accept
revised_at: 2026-11-14T15:41:03Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:sandbox-commit-gate-ceiling
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded the proposal PASS (draft PR #5179, 2026-11-13). On 2026-11-14 it gave this seat the next orchestrator revise slot, ahead of a-fleet-launcher-screens-an, whose sections are disjoint from this one. The proposal releases bd-ib-b3qjzq and bd-ib-vamn3n. Every re-entry brief after a refused or failed commit (implement_hook_route, fix and review_fix after a failed settle, and the open-Red routes) takes its failed targets and failing files from the commit run's full recorded output. It names up to 40 failing files with their uncovered lines or measured size, plus an omitted count, identically on every route. This closes the measured gap where a tail-only brief showed the per-target timing table instead of the uncovered file, in runs 01M75FQDD4SG and 01M75R19RPBJ. Accepted as written: the post-step doctor findings were folded in before #5179 merged, and the independent review found no blockers.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T15:40:30Z
verdict: NO BLOCKERS
proposal_stem: every-commit-refusal-re-entry
content_digest: ab1ff242c3d947ce94a8e420de6efe6a685f44f3d857a9cfe1ec0cb0b7d442a8
