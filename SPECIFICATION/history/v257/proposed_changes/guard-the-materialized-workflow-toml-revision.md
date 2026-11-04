---
proposal: guard-the-materialized-workflow-toml.md
decision: accept
revised_at: 2026-10-31T09:59:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-context-per-turn-reduction
---

## Decision and Rationale

Accepted as filed. The proposal generalizes §"Self-contained plugin dispatch", the target the spec-change tier classifier named, with two independent bounds on the materialized implement-work-item workflow.toml. A build-time check fails above 471,859 bytes (90 percent of Fabro's 524,288-byte limit). A dispatch-time refusal stops any dispatch over 524,288 bytes before claim. Both are grounded in measured failures: bd-ib-dsprir was refused at fabro-run at 526,975 bytes after its claim, and livespec-dev-tooling-2zii7l launched one byte under. It carries a BCP14 clause, a Gherkin Scenario 279 that exercises each behaviour, and the heading-coverage co-edit. It is placed in this repository's own contracts.md because it is Dispatcher realization mechanism. No ratified statement conflicts with it, and no design record is contradicted.

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
reviewed_at: 2026-10-31T09:58:56Z
verdict: NO BLOCKERS
proposal_stem: guard-the-materialized-workflow-toml
content_digest: 8a405e3f1a668340da905f0a64c3d70a9412ef93247cabc645172f60cc5ad8cb
