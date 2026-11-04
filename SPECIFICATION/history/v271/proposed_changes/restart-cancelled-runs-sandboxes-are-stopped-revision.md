---
proposal: restart-cancelled-runs-sandboxes-are-stopped.md
decision: accept
revised_at: 2026-11-01T22:58:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. Work-item bd-ib-lupvil, a child of plan kubernetes-sandbox-backend, carries the fix for restart-cancelled runs whose Kubernetes pods kept running and holding namespace quota (measured 2026-10-24 on gmktec: 8 of 24 cpu held for six hours, then a 403 quota refusal at sandbox acquire). It was refused at the R316 Definition-of-Done screen because no ratified heading governed restart-time sandbox cleanup. Coordinator legacy-coordinator-agent ruled the remedy on 2026-11-01: no split, ratify the governing clause first, and narrow the item from delete to stop. The clause extends the existing Sandbox retention and collection subsection. A stop releases compute and quota while leaving the driver record and workspace under the existing retention and collection rules, so nothing a human resolving a blocked or needs-human item needs is removed. The 'any other status' sentence is amended so it does not contradict the new rule. Scenario 295 states the behaviour. The independent reviewer's first pass found a blocker: the final bytes carried the sentence amendment, but the proposal did not record it. The proposal was amended, and the second pass returned NO BLOCKERS. The tests/heading-coverage.json entry for Scenario 295 lands in the same pull request, outside the spec tree. Re-cut 2026-11-02 against master at v270 (two other revisions took v269 and v270, and Scenarios 292 to 294), so the scenario is renumbered 295. The reviewer re-reviewed the re-cut bytes and returned NO BLOCKERS. This supersedes PR #4126.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T22:58:14Z
verdict: NO BLOCKERS
proposal_stem: restart-cancelled-runs-sandboxes-are-stopped
content_digest: 36dd3964cb57ca73cb028210b2425111fce06c09965c4224b10a24cd9ed594e5
