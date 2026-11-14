---
proposal: a-stale-preserved-seed-is.md
decision: modify
revised_at: 2026-11-14T00:55:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded PASS and gave the GO for this revise (2026-11-13, orchestrator revise slot after v373). It releases bd-ib-5xihdt's spec-change-tier hold (plan factory-run-work-preservation, epic bd-ib-nckst7): a stale seed is moved onto the default branch's tip by one authored diff-apply commit, never by a rebase. Its change 2 is applied to a-stale-seed-is-rebased-before-it-runs, ratified earlier in this same pass.

## Modifications

The scenario number is assigned: "## Scenario:" becomes "## Scenario 372 —", and the heading's first word is capitalized to "A", following the convention of every numbered scenario heading. 372 is the next free number: master's highest is 371, and no pending proposal or open spec pull request claims 372 or above (checked 2026-11-14 over every remote spec/* branch). The paragraph is placed after the paragraph a-seeded-dispatch-whose-seed inserts after the ruled-seed paragraph, as its change 1 directs. The tests/heading-coverage.json row carries the numbered heading (work item bd-ib-5xihdt), and tests/heading-coverage-debt.json is regenerated with `uv run python -m livespec_dev_tooling.heading_coverage_debt` in the same commit. The text is otherwise as graded.

One grade fix, on legacy-coordinator-agent's grade of #5213 (2026-11-14): after the sentence that says what the seed record names, the paragraph gains one sentence stating that it holds notwithstanding the paragraph "A seed taken from the item's own publish branch is read from the reclaim's preservation ref". A stale seed taken from the item's own publish branch is read from that preservation ref, and its seed record names the reseed ref and the reseed commit, names that preservation ref and the seed's commit as the source, and still names the publish branch. That way the two paragraphs cannot be read two ways.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T00:55:41Z
verdict: NO BLOCKERS
proposal_stem: a-stale-preserved-seed-is
content_digest: a3b56d595dba82be4fe4af306e25ca624d3c3a6224f40740b12abdb9b474f2f2
