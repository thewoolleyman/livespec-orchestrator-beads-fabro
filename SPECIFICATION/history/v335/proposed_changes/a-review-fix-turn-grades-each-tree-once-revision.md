---
proposal: a-review-fix-turn-grades-each-tree-once.md
decision: modify
revised_at: 2026-11-09T17:05:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

Accepted in substance under delegated decision mode, in the v335 slot legacy-coordinator-agent ruled on 2026-11-09 (decoupled from orchestrator-currency-surfaces-push-agents because the two touch different clauses). Every quoted anchor was rechecked on the v334 tree and matches exactly once. The paragraph's obligation now covers review_fix turns as well as fix turns, and the open-Red routing rule is stated explicitly: when fix_commit_settle or review_fix_commit_settle settles an open Red (TDD-Red trailers, no TDD-Green) as the turn's last commit, the run re-enters that stage for its Green amend instead of janitor_admission, and ends at needs_human naming the open Red at the stage's visit limit. Measured on bd-ib-d2qm5d run 01M6XF3D578K; the fix half is carried by bd-ib-7fdesc (b8a24670f), and the review_fix half is unmeasured but has the same unconditional graph shape. The independent read-only sonnet review found no blockers. Scenario 199's heading is unchanged and its coverage row is already TODO under bd-ib-fde4ie, so tests/heading-coverage.json needs no co-edit. After ratification, a review_fix implementation item is filed under bd-ib-qy5wol.

## Modifications

One change beyond the proposal's six edits. Edit 5 widens the Given line of Scenario 199's case 'A hook run that did not grade the tree, or a later change, still requires a passing commit' to 'a fix or review_fix turn', but the next line read 'When the fix turn is to complete successfully'. It now reads 'When the turn is to complete successfully', so the case's subject matches its widened Given. The proposal's other wording is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T17:04:13Z
verdict: NO BLOCKERS
proposal_stem: a-review-fix-turn-grades-each-tree-once
content_digest: 540c92e8f3dfd684c75bb97bfc28f195e83eea3ef6fd0ef85660499fa1e0adee
