---
topic: plan-identity-fields-on-the-read-projections
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T16:16:22Z
---

## Proposal: The read projections publish a plan epic's plan_slug, next_action and last_session

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The plan epic carries three plan-identity metadata keys (`plan_slug`, the typed `next_action` and `last_session`), but the `list-work-items --json` materialized view drops all three, and the `context` envelope carries `next_action` without `last_session`. A consumer that reads only these surfaces, such as the console's Plans roster, cannot render a plan record. This proposal adds the three keys to the `list-work-items --json` view (null on non-epic records) and `last_session` to the `context` envelope. Both are read-only projections of metadata the plan primitives already write.

### Motivation

Work-item bd-ib-wi5b, verified 2026-09-29 against the installed package: the WorkItem type has no field for the three keys, so they are dropped before the wire, and `LAST_SESSION_METADATA_KEY` is read nowhere in the context envelope. The livespec-console-beads-fabro Plans view consumes these surfaces and never derives plan facts locally, so the roster cannot be built until they are published. Plan spec-implementation-lockstep R1 batch 2 routes it here as an amendment of the two existing surface clauses.

### Proposed Changes

In SPECIFICATION/contracts.md, section "`list-work-items`", insert immediately AFTER the sentence ending "only `lane`/`lane_reason` are computed additions.":

> Each item whose type is `epic` MUST ALSO carry `plan_slug` (a string, or `null` when the epic has none), `next_action` (the typed object of §"Typed `next_action` and `last_session`" exactly as stored, or `null`) and `last_session` (a string, or `null`), read from the epic's metadata; every other item MUST carry `null` for all three. Scenario 216 in `scenarios.md` exercises this sentence.

In the same file, section "`context`", replace "its typed `next_action`;" with "its typed `next_action` and its `last_session`;".

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 216 — The read projections publish a plan epic's identity keys

```gherkin
Feature: A plan roster can be built from the read surfaces alone
  As a consumer that never derives plan facts locally
  I want the read projections to carry a plan epic's identity keys
  So that a plan record renders without reading raw metadata

  Scenario: An epic carries its plan keys and other records carry nulls
    Given a plan epic carrying plan_slug, next_action and last_session, and one non-epic work-item
    When list-work-items --json runs
    Then the epic's record carries all three keys with their stored values
    And the non-epic record carries null for all three

  Scenario: The context envelope carries last_session
    Given the same plan epic
    When context runs for its plan_slug with --json
    Then the envelope carries last_session beside next_action
```

