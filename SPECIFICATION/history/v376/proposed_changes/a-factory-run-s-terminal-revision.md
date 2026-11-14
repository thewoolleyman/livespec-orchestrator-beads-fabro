---
proposal: a-factory-run-s-terminal.md
decision: modify
revised_at: 2026-11-14T12:31:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Releases bd-ib-2h6cfl's hold (plan factory-run-yield assertion 2): failed runs' failure spans carry fabro.run_id, livespec.dispatch.id and a closed livespec.dispatch.failure_class, with fabro.failure.category rendering 'unreported' instead of None. Ratified under delegated decision in factory-run-yield's orchestrator revise slot (cut after v375 on legacy-coordinator-agent's queue, relayed by throughput-plans-coordinator); an independent read-only sonnet review reported NO BLOCKERS on these exact bytes.

## Modifications

The new scenario is numbered 373, and its gherkin is re-indented to scenarios.md's layout (Scenario lines at 2 spaces, steps at 4). The proposal wrote Scenario lines at column 0. The text is otherwise as proposed. tests/heading-coverage.json and tests/heading-coverage-debt.json gain the Scenario 373 TODO row owned by bd-ib-2h6cfl in the same change.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T12:31:12Z
verdict: NO BLOCKERS
proposal_stem: a-factory-run-s-terminal
content_digest: 32ddbcad6fd4d2db0a22ec77149965aa7365aa6e80f1b9ee6dcf8d90a76f4b6e
