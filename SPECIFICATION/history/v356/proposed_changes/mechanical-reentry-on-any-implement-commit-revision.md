---
proposal: mechanical-reentry-on-any-implement-commit.md
decision: modify
revised_at: 2026-11-11T22:45:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
---

## Decision and Rationale

Modified, then ratified. The ratified mechanical re-entry budget is written only against the four-node red/commit_red/green/commit_green graph, which was reverted to a single implement node in v0.288.0 (067118d96); its re-land (plan livespec-dev-tooling-sv6m5p) is not close. So no factory repository has a mechanical budget today. token-spend-analysis measured the aggregate-check blocked class (implement hook refused, re-entry budget exhausted, failing only on check-per-file-coverage and/or check-file-lloc) at 18 endings in 16 items and about $480 over the 7 days to 2026-11-11T18:12Z, rising; each ending is a purely mechanical refusal. The paragraph now governs every implement-stage commit the hook refuses, including the single implement node's. It adds a 40-file capped failing-file handoff (an uncapped embed caused the 2026-11-10 workflow.toml 512 KiB overflow), a wall-time guard so a mechanical re-entry cannot turn an aggregate-blocked ending into a wall-budget cancel, and a visit bound derived from both budgets that admits only mechanical re-entries. Four scenarios are appended inside Scenario 285, whose heading is unchanged, and the three existing mechanical scenarios stay true. legacy-coordinator-agent ruled the port conformance plus a generalization and graded the proposal PASS-WITH-FIXES, with all fixes in the proposal; implement-test-performance, owner of the split-graph re-land, agreed the shape. No H2 heading changes, so tests/heading-coverage.json is unchanged. No design record is cited by the paragraphs involved, and after the modification below the decision resolves no conflict between ratified statements. bd-ib-vamn3n implements it.

## Modifications

One sentence of the replacement paragraph is re-scoped. As proposed it read: 'it permits the workflow to run a single `implement` ACP node in place of that paragraph's four nodes until the four-node form is re-landed, and while it does, `implement` in this paragraph means that single node.' That would grant a spec-level permission contradicting the ratified MUST of 'The implement stage runs Red and Green as separate nodes' that the implement stage is realized as four nodes. It now reads: 'while the workflow runs a single `implement` ACP node in place of that paragraph's four nodes, `implement` in this paragraph means that single node. This paragraph grants no exemption from that paragraph's requirement that the implement stage be realized as four nodes.' Every behaviour the paragraph requires is unchanged. The single-node workflow's divergence from the four-node requirement stays an open conformance gap owned by the re-land plan, rather than being ratified away here.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T22:45:00Z
verdict: NO BLOCKERS
proposal_stem: mechanical-reentry-on-any-implement-commit
content_digest: 4c3384530be754ab76a73a332e326a93f9775727a5afdc1785d3805095a79fe2
