---
topic: host-routed-assertions-are-host-captured
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T16:41:13Z
---

## Proposal: A host-routed item's assertions are host-captured, and a factory_captured one is an advisory finding

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"The deliverable policy" makes an assertion carry the first proof mode that can prove it, and forbids `host_captured` for any assertion a published sandbox capability could exercise. That rule assumes a factory run exists. An item whose `factory_safety` is non-null is host-routed: no factory run ever executes it, so no sandbox capability can prove anything about it, and a `factory_captured` assertion on it can never be evidenced. This proposal states that, for such an item, the first mode that can prove an assertion is `host_captured` (or `human_attested` where no agent session on an operator host can exercise it). The sandbox-capability refusal does not apply to it, and a `factory_captured` assertion on it is an ADVISORY Definition-of-Done finding naming the assertion, the item's `factory_safety` reason and the remedy. The run-id binding of factory records is unchanged.

### Motivation

Work-items bd-ib-rowuou and bd-ib-gv6uwy. 14 host-routed items in the livespec-dev-tooling tenant parked at acceptance with "merging run id unavailable" because a factory_captured assertion can be evidenced only by a verified record naming a merging factory run, and each had to be closed by hand. The latest instance is livespec-dev-tooling-jvem (2026-10-17/18), which came through driver-dispatch. Nothing at filing, intake or driver-dispatch warns. The definition-and-proof-of-done owner chose a filing-time WARNING over a refusal, as recorded on bd-ib-rowuou, so the finding is advisory. Plan spec-implementation-lockstep R1 batch 3 routes both items here as one amendment of the deliverable policy, because both are the same gap: the policy presumes a factory run that a host-routed item never has.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance" → "Effective acceptance criteria", paragraph "The deliverable policy.", insert the following sentences immediately AFTER the sentence ending "is still captured mechanically.":

> More generally, an item whose `factory_safety` is non-null is host-routed (§"Admission valve (`ready → active`)") and no factory run executes it, so no sandbox capability can prove any of its assertions. For such an item the first mode that can prove an assertion is `host_captured`, or `human_attested` where no agent session on an operator host can exercise it, and the sandbox-capability refusal above MUST NOT be applied to it. A `factory_captured` assertion on such an item MUST be reported by the host-side wall as an ADVISORY Definition-of-Done finding naming the assertion, the item's `factory_safety` reason and the remedy of moving the assertion under a `### Host-captured` sub-heading with a `Reason:` line. The finding MUST NOT withhold `ready`. The binding of a `factory_captured` record to the merging dispatch's run identifier is unchanged. Scenario 217 in `scenarios.md` exercises these sentences.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 217 — A host-routed item's factory_captured assertion is an advisory finding

```gherkin
Feature: A host-routed item never carries a proof mode it can never satisfy
  As an operator filing work that only a host can run
  I want the wall to flag a factory_captured assertion on it
  So that the item does not park at acceptance waiting for a factory run that never comes

  Scenario: A factory_captured assertion on a host-routed item is flagged
    Given a work-item whose factory_safety is mutates-host-machinery
    And its Definition of Done carries a factory_captured assertion
    When its filing is displayed
    Then an advisory Definition-of-Done finding names that assertion and the factory_safety reason
    And the finding names the remedy of moving it under a Host-captured sub-heading with a Reason line
    And the finding does not withhold ready

  Scenario: A host-routed item may declare a sandbox-exercisable assertion host-captured
    Given a work-item whose factory_safety is non-null
    And its Host-captured assertion names behaviour a published sandbox capability could exercise
    When its filing is displayed
    Then no Definition-of-Done finding refuses the Host-captured declaration

  Scenario: A factory-eligible item keeps the sandbox-capability refusal
    Given a work-item whose factory_safety is null
    And its Host-captured assertion names behaviour a published sandbox capability could exercise
    When the gate grades it
    Then the gate refuses the Host-captured declaration naming that sandbox capability
```

