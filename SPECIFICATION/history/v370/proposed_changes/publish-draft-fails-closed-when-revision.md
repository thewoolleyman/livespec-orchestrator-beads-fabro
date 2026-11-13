---
proposal: publish-draft-fails-closed-when.md
decision: modify
revised_at: 2026-11-13T16:17:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision after legacy-coordinator-agent graded proposal PR #5160 PASS. It releases bd-ib-hzul2n's spec-change-tier hold. This decision's resulting files carry both proposals' edits, because the revise applies decisions in order and the later full-file write must keep the earlier one. Independent read-only ratification review (configured reviewer model sonnet): NO BLOCKERS. Non-blocking notes carried forward: (1) the fold paragraph's no-authored-commit fail-closed and the landed-publication check are not ordered against each other; an implementer runs the landed check first, as that paragraph places it before any push; (2) a hook refusal of the folded commit fails closed with the hook's own output but names no error code; (3) the hook-refusal, no --no-verify and existing-tip-exemption clauses, and the adopt paragraph's failed re-read and other-scripted-step clauses, have no dedicated scenario; the main behaviours of each paragraph do; (4) the refresh paragraph's later sentence "publish_draft still publishes the janitor-passed head" reads loosely beside a folded commit, but the amended sentence before it covers that.

## Modifications

The only modification is the scenario number: "<number assigned at revise>" becomes 369, in both the scenario heading and the paragraph's closing sentence. The number is the next free one: master's highest was 367, and no open pull request or pending proposal claims a higher one. The text is otherwise ratified exactly as proposed. Co-edits outside the spec target, in the same commit: one tests/heading-coverage.json TODO row for Scenario 369 (work_item bd-ib-hzul2n, integration tier or above), and tests/heading-coverage-debt.json regenerated with `uv run python -m livespec_dev_tooling.heading_coverage_debt`.

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
proposal_stem: publish-draft-fails-closed-when
content_digest: 3e8d1db9df8a9dece0e142735bc84301b353f3eac23e05a4053e32255fa1c9ec
