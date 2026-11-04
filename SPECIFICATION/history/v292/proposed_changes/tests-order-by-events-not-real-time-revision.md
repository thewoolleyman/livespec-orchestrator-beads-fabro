---
proposal: tests-order-by-events-not-real-time.md
decision: modify
revised_at: 2026-11-04T04:32:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:seat:spec-implementation-lockstep
---

## Decision and Rationale

Ratify the Forbidden-patterns rule against real-time sleeps and wall-clock verdicts in tests, with its refusing just-check check and reasoned per-line exemption marker, under the delegated revise mode at the request of legacy-coordinator-agent for fleet-flaky-tests (priority 3). It is the governing clause bd-ib-ke5wkf's Definition of Done needs before dispatch. The clause is taken verbatim; it contradicts no existing clause, and the only wall-clock rules elsewhere govern the Dispatcher watchdog and headroom, not tests.

## Modifications

The scenario is numbered 304 (the next free number) and reformatted into the file's house Gherkin style (a Feature line and an indented Scenario), with the proposal's second Given/When/Then round expressed as a further When/Then of the same scenario; its meaning is unchanged. The scenario is inserted directly after Scenario 303, ahead of the unnumbered scenarios. A tests/heading-coverage.json entry for the new H2 is added with test TODO and an integration-tier owed-test reason, owned by bd-ib-ke5wkf. The constraints.md bullet is appended verbatim as the last Forbidden-patterns bullet.

## Resulting Changes

- constraints.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T04:32:31Z
verdict: NO BLOCKERS
proposal_stem: tests-order-by-events-not-real-time
content_digest: 73fbab5ff3de49932a5f1cb016a9fdfebb6e9ee6d34d454a35faab5f308d95e7
