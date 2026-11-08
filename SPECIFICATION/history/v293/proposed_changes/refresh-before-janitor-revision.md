---
proposal: refresh-before-janitor.md
decision: modify
revised_at: 2026-11-04T06:56:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted design (legacy-coordinator-agent, R301 delegation, 2026-11-04). Moving the refresh onto the default branch to the start of the janitor visit that precedes publish_draft makes the full check aggregate run once, on the tree that is pushed, so publish_draft's push honours the recorded green verdict under 'Pre-push gate refinements'. That removes the second full aggregate measured in 18 of 22 runs reaching publish_draft, and the 7 publish_draft push hook-over-limit endings in 12 h, with no check removed. Refresh repair covers the janitor's refresh unchanged.

## Modifications

Placement and consistency only. Beyond the proposal's listed edits, the same rule was applied to every other sentence or scenario that said publish_draft refreshes: the agent-stage publication-boundary merge base, the declared-record-files paragraph, constraints.md's Scenario 253 example (now pr_refresh), and the Scenario 176 sub-scenarios (now starting from the agent stage's head and the janitor's pre-aggregate refresh), plus Scenario 256 ('When publish_draft runs, before it pushes'), and the scenario steps at about lines 7877 and 7968. In the new paragraph, 'the same refresh mechanism publish_draft uses today' became 'used before this paragraph', so the spec does not contradict itself. Scenario 305 was added after Scenario 304, and its tests/heading-coverage.json entry is TODO, carried by bd-ib-fvgkw4.

## Resulting Changes

- contracts.md
- scenarios.md
- constraints.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T06:54:53Z
verdict: NO BLOCKERS
proposal_stem: refresh-before-janitor
content_digest: 4cb511837e69df37f17654e723e8cc19a315a3487f8c80fbeff58aec81d85fdf
