---
topic: the-spec-change-hold-is
author: claude-opus-5-5
created_at: 2026-11-11T02:47:04Z
---

## Proposal: The spec-change hold covers every classification, and classify-tier re-judges an item whose text or spec identity changed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two changes. First, an item classified bug, chore or non_functional is spec-change tier whenever the spec-stated judgement reports its asked-for behaviour partial or unstated, so the judgement is always taken. Second, classify-tier re-judges an item whose latest tier record's behaviour digest or spec identity no longer matches, instead of always reporting the first record. One scenario covers both.

### Motivation

Two ratified sentences let a behaviour change the spec does not state reach ready and dispatch. 'An item classified bug, chore or non_functional is never spec-change tier' skips the judgement (verdict-kind: (not taken)), and classify-tier 'MUST append nothing' when any record exists. Cases: bd-ib-p6ammc (recovery routing holds a recapture-exhausted run) was classified bug at filing on 2026-11-11 and routed ready at tier none although its behaviour is unstated; retyping it and running classify-tier changed nothing, and it was caught by hand. livespec-dev-tooling-7salp4 was typed feature but its dispatch tier record reads 'classification: bug, verdict-kind: (not taken)' while its DoD judgement reported governing-heading-kind: unstated. Filed on legacy-coordinator-agent's ruling (2026-11-11) as the linked proposal of bd-ib-t2rg6x, whose tier record names this topic stem, in plan publish-draft-green-work-loss (epic bd-ib-acrr56).

### Proposed Changes

Two ratified sentences MUST change.

1. In SPECIFICATION/contracts.md §"Grooming and slice-size calibration", the autonomy-tier sentence MUST read:

"An item classified `bug`, `chore` or `non_functional` is spec-change tier when the spec-stated judgement reports its asked-for behaviour `partial` or `unstated`, exactly as an item classified `feature` is. It routes as every other factory-dispatchable item only when that judgement reports the behaviour `stated`."

It replaces "An item classified `bug`, `chore` or `non_functional` is never spec-change tier and routes as every other factory-dispatchable item." The judgement MUST therefore be taken for every implement-kind item at filing, at groom and on every dispatch path, whatever its classification. A spec-change tier record MUST NOT carry `verdict-kind: (not taken)` for an implement-kind item.

2. In SPECIFICATION/contracts.md §"Dispatcher classify-tier invocation surface", the bullet "When the item already carries a `livespec-spec-change-tier` record, it MUST append nothing and MUST report the existing classification." MUST be replaced by two bullets:

- "When the item's latest `livespec-spec-change-tier` record carries a behaviour digest equal to the item's current behaviour digest, and was taken against the current spec identity, it MUST append nothing and MUST report the existing classification."
- "When the item's latest record's behaviour digest or spec identity differs from the item's current one, it MUST take the judgement afresh and append exactly one new record with `stage: classify`, and the hold MUST apply when that record is a held spec-change tier."

This aligns classify-tier with the existing verdict-reuse rule: a verdict is reused only while its input and spec identity are both unchanged since it was taken.

In SPECIFICATION/scenarios.md, one new scenario MUST be added (the revise pass MAY renumber it):

## Scenario 344 — An item classified bug whose asked-for behaviour the spec does not state waits for ratification, and classify-tier re-judges a changed item

```gherkin
Feature: The spec-change hold covers every classification and follows the item's current text
  Scenario: A bug-classified ask for unstated behaviour is held
    Given an implement-kind item that the classifier classifies bug
    And the spec-stated judgement reports its asked-for behaviour unstated
    When the item is filed
    Then its spec-change tier record reads tier spec-change with a linked proposed-change topic
    And the item is held out of ready
  Scenario: A bug restoring stated behaviour routes as before
    Given an implement-kind item classified bug whose asked-for behaviour the judgement reports stated
    When the item is filed
    Then its tier record reads tier none and the item routes as every other factory-dispatchable item
  Scenario: classify-tier re-judges a changed item
    Given an item whose latest spec-change tier record reads tier none with a behaviour digest
    And the item's body has since changed so its current behaviour digest differs
    When classify-tier runs on the item
    Then it appends one new record from a fresh judgement
    And when that record is a held spec-change tier the item is held
```

Per this repository's revise co-edit discipline, the revise pass MUST add tests/heading-coverage.json and tests/heading-coverage-debt.json rows for the new heading, owned by bd-ib-t2rg6x.
