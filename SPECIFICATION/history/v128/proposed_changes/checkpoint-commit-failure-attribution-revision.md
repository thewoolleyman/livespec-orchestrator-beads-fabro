---
proposal: checkpoint-commit-failure-attribution.md
decision: modify
revised_at: 2026-10-12T17:39:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

No ratified heading governs a Fabro run that ends on a failed engine checkpoint commit, so the factory Definition-of-Done gate refused bd-ib-6jkjzm (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq; refusing run 01M4RGVVFBVM0Y11CHG9DV0QS2). This ratifies the plan's existing assertion that such a run leaves its item blocked with a reason naming the node and the failed hook targets, with its tree preserved. It reuses the janitor's structured-summary rule (v123) rather than adding a parser, rests the item at the existing needs-human reason so blocked_reason gains no member, and keeps exit code 4 under the existing table. Measured 2026-10-12 on hp: 41 of 215 workflow_error runs since 2026-10-08 ended on a checkpoint failure (28 hook refusals, 8 budget expiries, 5 git add failures), each journaled without its cause and left active, so items were re-dispatched unchanged. No cited design record is contradicted. Independent read-only review by OpenAI Codex gpt-6-astra (the configured ratification_reviewer_model): first pass, Codex session 01a1312e-44c3-7ab2-9fb2-8b6f49c448a8, returned one blocker; second pass on the final bytes, Codex session 01a13130-5457-7083-a8fd-952b643c53c3, returned NO BLOCKERS.

## Modifications

1. Blocker fix (reviewer replacement text applied verbatim): the outcome-detail attribution list now reads 'the failed targets and/or failed hook commands; the labelled observation; the configured budget with the engine's measurement, or an explicit configured-budget-unavailable reason; or the engine's checkpoint error alone when no output tail is available', so the git add failed case the clause and Scenario 170 require is permitted. 2. Reviewer's non-blocking suggestion applied: when the run's events cannot be read, terminal_patch_bytes and terminal_patch_sha256 are null, both records state the terminal patch is unavailable with the reason, and they MUST NOT state the run carried no work; Scenario 170's unreadable-events sub-scenario gains the matching Then line. Heading coverage: tests/heading-coverage.json gains a Scenario 170 TODO row and tests/heading-coverage-debt.json a matching row (first_seen 2026-10-12), both owned by bd-ib-6jkjzm.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-12T17:38:13Z
verdict: NO BLOCKERS
proposal_stem: checkpoint-commit-failure-attribution
content_digest: e856da81d3482df4ed10f65120b514fb2c3a2ace054086ba5f82e60a085af7e6
