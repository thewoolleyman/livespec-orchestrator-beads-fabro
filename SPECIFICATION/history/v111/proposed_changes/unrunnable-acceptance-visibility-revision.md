---
proposal: unrunnable-acceptance-visibility.md
decision: modify
revised_at: 2026-09-12T13:44:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: codex-gpt-5.6-sol
---

## Decision and Rationale

Accept every behavioral requirement with one sequencing correction: a green integration test cannot honestly bind an unimplemented scenario during the spec-only ratification without being skipped, expected-failing, or falsely partial. Record the owned integration-tier TODO atomically now; require the immediately filed implementation mirror to land the real Scenario 128 integration test and replace the TODO before livespec-n33rwg.10 can complete.

## Modifications

Modify only the proposal's final revise-time heading-coverage instruction: this ratification atomically registers Scenario 128 as an owned TODO whose reason explicitly requires integration-tier coverage, because the candidate-visibility behavior is not implemented yet. The immediately required post-revise implementation mirror MUST add the real integration-tier scenario test, replace that TODO with its node id, and cannot complete while the TODO remains. All candidate filtering, hygiene visibility, control, pagination, and explicit-dispatch-wall requirements remain unchanged.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-12T13:32:11Z
verdict: NO BLOCKERS
proposal_stem: unrunnable-acceptance-visibility
content_digest: 4c962fdb089d6dc2c7cf8625eded1aa222a5d961d0e0f4d97d42dc0a6cde08ba
