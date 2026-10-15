---
proposal: checkpoint-failed-tree-preservation.md
decision: accept
revised_at: 2026-10-15T14:54:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-checkpoint-commit-hook-failures
---

## Decision and Rationale

Accepted verbatim. The proposal on master is the Fable-approved rework (PR 3054, e49f6c74). PR 3052 had auto-merged an earlier draft that the freeze driver's Fable review blocked, because suppressing publication on a stage diff artifact would lose the failed node's work; the rework keys trigger and suppression on an observed terminal patch alone. Fable review (freeze driver, session gitops-fleet-capacity-monitoring): BLOCK on 924f83ed, APPROVE on c78a645c, APPROVE on the delta to aef4c12c. Independent ratification review (gpt-6-astra, read-only): rounds 1, 3 and 4 returned BLOCKERS, each fixed in the proposal before it merged: the unreadable-events partition, the recovery-seed checkout conflict, and the recovery-source preference order. Round 5 returned NO BLOCKERS on the proposal; round 6 (codex session 01a1400c-9dee-72e1-856a-885450295426) returned NO BLOCKERS on these final bytes against master after the session-headroom v143. Decision authority: the maintainer authorized the freeze driver to approve spec revises after a Fable review, recorded on livespec-dev-tooling-dfixhe (2026-10-15T00:08Z and 00:22Z); the driver directed this revise. This session did not receive that authorization from the maintainer directly. Step 3.5 note: the stale-branch precondition was skipped explicitly for its only finding, spec/plan-proof-release-rule-names-the-build-repository (owner k3s-on-gmktec-for-vps-usage), which adds only its own proposed-change file; the driver authorized that skip. The driver refused a skip for spec/revise-session-headroom-burn-projection, so this revise waited for that branch to land as v143 and is cut as v144. Implementation carrier: bd-ib-na2xvm (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq), which owns the Scenario 183 heading-coverage TODO and debt row added in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T14:53:46Z
verdict: NO BLOCKERS
proposal_stem: checkpoint-failed-tree-preservation
content_digest: 1b0a9b424f1a11489543be19a29bba16ed6e186274619942c2699a88c1fd49a2
