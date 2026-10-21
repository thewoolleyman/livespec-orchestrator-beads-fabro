---
topic: rendered-goal-reach-and-size-advisories
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:00:34Z
---

## Proposal: A brief that points its implementer at another work-item's evidence carries an advisory finding

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The rendered goal is assembled from the dispatched item's own fields and ledger comments, and the sandbox has no ledger access. So an item whose text says that its evidence lives in ANOTHER work-item's comments sends the implementer to something it cannot read, and every existing wall passes it. This proposal adds that case to the ADVISORY findings of "Authoring at filing time". The wall reports it naming the referenced work-item, with the remedy of carrying the evidence onto this item. Because the detection is advisory, it never refuses, and an item it does not flag is not thereby cleared.

### Motivation

Work-item bd-ib-n1kn, measured 2026-08-23 in the livespec-overseer tenant: ten open rows carried a sentence pointing at a predecessor's comments as their evidence, all filed in one wave when three plans archived. Per-row measurement by two seats found real evidence loss on some of them. The item's own analysis records that any mechanical discriminator is high-precision and low-recall, so it must never be used to clear a row. That is exactly the advisory posture the paragraph already defines for findings only the gate can judge. Plan spec-implementation-lockstep R1 batch 4 routes it here as an amendment of that paragraph.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance" → "Effective acceptance criteria", paragraph "Authoring at filing time.", insert the following sentences immediately AFTER the sentence ending "because only the gate can judge it.":

> The rendered goal is assembled from the dispatched item's own fields and ledger comments, and the sandbox has no ledger access. So a description, Definition of Done or comment that names another work-item as holding this item's evidence directs the implementer to text it cannot read. The wall MUST report such a reference as an ADVISORY finding naming the referenced work-item, with the remedy of copying the evidence onto this item before dispatch. An item the wall does not flag MUST NOT be reported as clear of such references. Scenario 218 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 218 — A brief pointing at another work-item's evidence carries an advisory finding

```gherkin
Feature: The implementer is never sent to evidence it cannot read
  As a filer writing a successor item
  I want the wall to flag a pointer to another item's comments
  So that the evidence travels with the item the factory runs

  Scenario: A pointer to a predecessor's comments is flagged
    Given a work-item whose description says its evidence is in the comments of work-item bd-ib-example
    When its filing is displayed
    Then an advisory Definition-of-Done finding names bd-ib-example
    And the finding names the remedy of copying that evidence onto this item
    And the finding does not withhold ready
```


## Proposal: A rendered goal larger than a configured bound carries an advisory finding

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every ledger comment on an item is rendered into its dispatch goal, and comments are append-only, so evidence recorded on an item grows the brief that an unattended run must finish, and nothing warns. This proposal adds an optional Dispatcher policy setting, `dispatcher.goal_size_warning_bytes`. When it is set, an item whose rendered goal exceeds it carries an ADVISORY finding naming the item and the size, shown by the filing displays, by the Dispatcher when it renders the goal, and among the `needs-attention` hygiene facts. It never refuses or delays a dispatch. With the key unset, nothing changes.

### Motivation

Work-item bd-ib-40vz: item overseer-6s3pk6.6 grew to 10,862 bytes, roughly seven times its five siblings, purely from three comments recording live measurements. Nothing warned, and it was found only because a pre-flight happened to measure it. The fleet's guidance to record evidence on the ledger and the dispatchability of the same item are in direct conflict, and only a surfaced size can show an author the cost. R290 triage confirmed on master that only the calibration journal's dispatch context size is recorded, and that the sizing warnings read only title and description. A committed bound, rather than an invented default, follows the existing rule that numeric policies come from committed configuration. Plan spec-implementation-lockstep R1 batch 4 routes it here as an amendment of the advisory-findings paragraph.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance" → "Effective acceptance criteria", paragraph "Authoring at filing time.", insert, after the sentences the previous proposal of this file adds there (or, if that proposal is rejected, immediately after that same sentence), the following sentences immediately AFTER the sentence ending "because only the gate can judge it.":

> When the committed Dispatcher policy setting `dispatcher.goal_size_warning_bytes`, a positive integer with no default, is set, an item whose rendered goal exceeds it MUST carry an ADVISORY finding naming the item and the rendered goal's size in bytes. The rendered goal here means title, description, criteria, notes, lessons and every ledger comment. The finding MUST be shown by the filing displays and by the Dispatcher's stderr and dispatch journal when it renders that goal, and MUST be among the `needs-attention` hygiene facts for a `ready` item. It MUST NOT refuse or delay a dispatch. When the key is unset, the finding MUST NOT be evaluated, and an invalid value MUST be reported as a configuration finding. Scenario 219 in `scenarios.md` exercises these sentences.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 219 — A rendered goal larger than the configured bound carries an advisory finding

```gherkin
Feature: An author sees what recorded evidence costs the brief
  As an operator recording measurements on a work-item
  I want an oversized rendered goal flagged
  So that the item does not silently become too large to finish unattended

  Scenario: A goal over the bound is flagged without refusing
    Given dispatcher.goal_size_warning_bytes is committed as 8000
    And a ready work-item whose rendered goal, comments included, is 10862 bytes
    When the Dispatcher renders its goal
    Then an advisory finding names the item and 10862 bytes on stderr and in the dispatch journal
    And the dispatch proceeds

  Scenario: No bound means no finding
    Given dispatcher.goal_size_warning_bytes is not set
    When the Dispatcher renders any goal
    Then no goal-size finding is reported
```

