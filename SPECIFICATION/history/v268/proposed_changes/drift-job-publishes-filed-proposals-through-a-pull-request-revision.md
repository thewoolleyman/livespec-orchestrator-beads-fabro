---
proposal: drift-job-publishes-filed-proposals-through-a-pull-request.md
decision: accept
revised_at: 2026-11-01T15:33:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT. Amends the existing 'The drift run.' bullet of contracts.md and Scenario 207 in place, adding no H2 heading: a drift-job run MUST NOT write into its --repo working tree, MUST write its filed proposals in a fresh worktree of the fetched default branch, commit them on one spec/ branch and publish ONE pull request per run; a finding is filed only once that pull request exists, so a failed commit or publication leaves the frontier behind those merges; the already-filed identity set and the dispatcher.drift_proposal_queue_cap open count include proposals on open drift-run pull requests. Motivation: bd-ib-mztpy7 (the drift lane left five untracked drift-*.md files in the primary checkout, 2026-10-24..30, and factory run 01M66V2ACN0K ended at implement_amendment_route for want of this clause); drift-run is now the drift job entry point, so the plan's metered drift batch would repeat the defect. Contradicts no design record. Decided under delegated revise_decision_mode by plan session spec-implementation-lockstep (epic bd-ib-ax3rds), executing the epic's recorded next action. Independent read-only sonnet review: NO BLOCKERS on these exact bytes; nits left for later passes: contracts.md ~line 3411 still says 'the drift run of each Dispatcher reconcile pass' (pre-existing stale wording), and 'on the run's pull request' is loose once that pull request has merged. tests/heading-coverage.json unchanged (no H2 change).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T15:31:09Z
verdict: NO BLOCKERS
proposal_stem: drift-job-publishes-filed-proposals-through-a-pull-request
content_digest: 9c38522f8107b8049c1e39a028659178eb0c399c92cff397833664fb01aa1a1f
