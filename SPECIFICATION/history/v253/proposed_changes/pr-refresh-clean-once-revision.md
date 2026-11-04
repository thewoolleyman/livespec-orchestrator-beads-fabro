---
proposal: pr-refresh-clean-once.md
decision: accept
revised_at: 2026-10-28T06:04:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted, spec-first for bd-ib-6sugaf (coordinator ruling R150, routed by petri-factory-on-gmktec): clean refreshes counted toward pr_refresh's three-refresh bound, so finished, proven runs on a busy default branch ended pr-refresh-non-converged. A separate read-only Claude Sonnet reviewer, the configured ratification reviewer, raised blockers in rounds 1 and 2 (a stale scenario step, an unconditional sentence, then two sentences that contradicted the conflict-re-entry counting); each was adopted and the proposal re-filed, and round 3 returned NO BLOCKERS at 2026-10-28T06:04:47Z. A run refreshes cleanly at most once and leaves later default-branch movement to the merge path; only counted refreshes reach the bound.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-28T06:04:47Z
verdict: NO BLOCKERS
proposal_stem: pr-refresh-clean-once
content_digest: 2ace5642aeecdb21143d2d5a73d0b553af8b8a641a124cceec7f8bf6aeac05b6
