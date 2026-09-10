---
topic: set-factory-safety-operator-verb
author: claude-code (mechanically-enforce-factory-usage)
created_at: 2026-09-09T15:33:04Z
---

## Proposal: set-factory-safety operator verb

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a set-factory-safety:<id>:<reason> operator verb that sets the already-shipped factory_safety opt-out field with a mandatory rationale, giving factory-eligibility opt-out a first-class, journaled valve instead of the current raw label edit.

### Motivation

The factory_safety field is the intrinsic host-only runnability axis, orthogonal to admission_policy, and it already exists as a first-class work-item field. There is no operator verb to SET it: the only current path to opt an item out of factory eligibility is a raw `bd label add`, which is exactly the unrecorded hand-edit shape the factory-usage enforcement is meant to eliminate. Plan mechanically-enforce-factory-usage (epic bd-ib-btr5do in the livespec-orchestrator-beads-fabro tenant) requires opting an item out of factory eligibility to be a recorded, reasoned act. The valve implementation is tracked at work-item bd-ib-jhn2jw and is gated on this ratification.

### Proposed Changes

Add `set-factory-safety:<id>:<reason>` to the ready-lane valid operator verb set in the section 'Per-lane valid operator verb sets', and add a normative clause defining the verb. The clause MUST specify: the verb sets the target work-item's factory_safety field to the supplied host-only reason; the reason MUST be non-empty; the default (a null factory_safety) remains factory-eligible; opting an item out of factory eligibility MUST go through this verb so the reason is recorded on the item, rather than through a raw label edit. The verb is valid only in the ready lane and MUST NOT alter admission_policy, which is the orthogonal human-approval axis. During the revise that ratifies this, update tests/heading-coverage.json in the same change if a new heading is introduced.
