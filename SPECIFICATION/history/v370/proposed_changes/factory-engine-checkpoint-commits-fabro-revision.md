---
proposal: factory-engine-checkpoint-commits-fabro.md
decision: modify
revised_at: 2026-11-13T16:17:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision after legacy-coordinator-agent graded proposal PR #5159 PASS (after one grade fix: fold only with exactly one authored commit; more than one beside non-authored commits fails closed). It releases bd-ib-ffw4q3's spec-change-tier hold. Independent read-only ratification review (configured reviewer model sonnet): NO BLOCKERS. Non-blocking notes carried forward: (1) the fold paragraph's no-authored-commit fail-closed and the landed-publication check are not ordered against each other; an implementer runs the landed check first, as that paragraph places it before any push; (2) a hook refusal of the folded commit fails closed with the hook's own output but names no error code; (3) the hook-refusal, no --no-verify and existing-tip-exemption clauses, and the adopt paragraph's failed re-read and other-scripted-step clauses, have no dedicated scenario; the main behaviours of each paragraph do; (4) the refresh paragraph's later sentence "publish_draft still publishes the janitor-passed head" reads loosely beside a folded commit, but the amended sentence before it covers that.

## Modifications

The only modification is the scenario number: "<number assigned at revise>" becomes 368, in both the scenario heading and the paragraph's closing sentence. The number is the next free one: master's highest was 367, and no open pull request or pending proposal claims a higher one. The text is otherwise ratified exactly as proposed. Co-edits outside the spec target, in the same commit: one tests/heading-coverage.json TODO row for Scenario 368 (work_item bd-ib-ffw4q3, integration tier or above), and tests/heading-coverage-debt.json regenerated with `uv run python -m livespec_dev_tooling.heading_coverage_debt`.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T16:16:28Z
verdict: NO BLOCKERS
proposal_stem: factory-engine-checkpoint-commits-fabro
content_digest: 1b1a72237227aa7403a8bf3055c0b3d7a431610923bf4724348f44e4c49b49a4
