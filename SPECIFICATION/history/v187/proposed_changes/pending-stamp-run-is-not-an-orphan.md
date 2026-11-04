---
topic: pending-stamp-run-is-not-an-orphan
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:22:45Z
---

## Proposal: A run attributed to an item whose claim carries a pending stamp is not an orphan

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Stranded claim release" replaces an item's run stamp with a PENDING stamp at admission, so that "a newly admitted dispatch that has not yet learned its run can never be read as the previous claim". The run-half orphan rule of "A factory run never awaits a human" still calls a run an orphan when its item is `active` under a different JOURNALED run id. A just-launched run, whose own stamp has not landed yet, therefore reads as superseded by its item's previous run, and a sibling reconciler or watchdog sweep cancels it. This proposal states the run-half consequence of the pending stamp: while an item's claim carries a pending stamp, a non-terminal run attributed to it is not an orphan.

### Motivation

Work-items bd-ib-m1av and bd-ib-cewr.5. Measured 2026-09-06 in livespec-dev-tooling: engine B's preflight reconcile-runs cancelled engine A's 18-second-old run 01M1VPM6S3DC for livespec-dev-tooling-thw26i as superseded-run, because the journal's newest run id for the item was a run from 2026-08-21. Measured 2026-09-08 in the console tenant: a concurrent dispatch's discovery poll cancelled three freshly created runs of re-dispatched items the same way, with zero inference spent. The claim half was already protected by the pending stamp; the run half was not. Plan spec-implementation-lockstep R1 batch 5 routes both here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "A factory run never awaits a human", in the bullet beginning "The Dispatcher MUST reconcile every configured factory's non-terminal run inventory against the ledger.", insert immediately AFTER the sentence that defines an ORPHAN, which ends "the orphan reason, and the termination route.", and BEFORE the sentence beginning "The export is the precondition":

> An item whose claim carries a pending stamp (§"Stranded claim release") is not `active` under a different journaled run id: while the stamp is pending, a non-terminal run attributed to that item MUST NOT be classified an orphan, so no reconciler or watchdog sweep may terminate the run its own dispatch has just created. Scenario 223 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 223 — A run attributed to an item under a pending stamp is not an orphan

```gherkin
Feature: A sibling sweep never cancels a run its own dispatch just created
  As an operator running two dispatcher engines on one host
  I want a just-launched run protected until its stamp lands
  So that a sibling's reconcile pass does not cancel live work

  Scenario: A pending stamp protects a fresh run
    Given an item admitted with a pending stamp and a previous journaled run id from an earlier dispatch
    And a non-terminal run attributed to that item whose run stamp has not been written yet
    When another Dispatcher's reconcile-runs pass runs
    Then the run is not classified an orphan and is not terminated

  Scenario: A superseded run is still an orphan
    Given an item whose claim carries a run stamp naming run B
    And a non-terminal run A attributed to the same item
    When a reconcile-runs pass runs
    Then run A is classified an orphan with reason superseded-run
```

