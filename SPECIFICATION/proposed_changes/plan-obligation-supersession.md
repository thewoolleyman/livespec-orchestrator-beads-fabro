---
topic: plan-obligation-supersession
author: claude-fable-5-1:spec-implementation-lockstep
created_at: 2026-10-20T13:12:05Z
---

## Proposal: An unmet plan obligation can be superseded by a typed, evidenced event, and never by a rename

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Required result, budget and progress epoch" says a replacement or renaming of an unmet result MUST preserve the original obligation until "an evidenced causal supersession explicitly accounts for it". The phrase is used but never defined, and no writer can record one. So an obligation that should not exist cannot be replaced by any sanctioned path before it expires. This proposal defines the supersession event and its closed set of causes, each with machine-checkable evidence. It is accepted only through the two sanctioned pointer writers. It never resets or postpones the original deadline or the consumed handoff count, and the replacement inherits both.

### Motivation

Plan spec-implementation-lockstep (epic bd-ib-ax3rds), measured 2026-10-20. An `append_handoff` advanced a satisfied obligation to a new required result as epoch 14. Twenty-six seconds later, a `resume_directive` call read the previous obligation off the chain, judged it satisfied, and persisted a derived `impl:bd-ib-j6uvkj` as epoch 15, with required result bd-ib-j6uvkj closed. That item is host-routed, so the derived step was wrong in kind. Every attempt to restore the intended result was then refused with "the unmet obligation ... cannot be renamed ... without evidenced causal supersession". The only remaining paths were to wait for expiry or to hold the pointer at `human`. The prevention defect is filed as bd-ib-wnrird. This proposal supplies the recovery the clause already presumes: a supersession whose cause is verifiable, so that a mis-derived or disposed obligation can be retired without letting a relabel evade expiry. It mirrors the explicit supersession §"Relay delivery" already requires for a conflicting relay target.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Planning Lane realization" → "Required result, budget and progress epoch", insert the following paragraph immediately AFTER the paragraph that ends "a new label, repair-child milestone, acknowledgment or changed-approach claim cannot evade expiry.":

> **An evidenced causal supersession** is a typed event that replaces an unmet obligation's required result. It is accepted ONLY through `set_next_action` or `append_handoff` carrying it, and it MUST be recorded as a `plan-progress-event` of kind `supersession` before the pointer changes. It MUST name the superseded obligation's canonical result identity and epoch, the replacement required result, exactly one cause, the evidence identifiers that cause requires, and the writer. The causes are a closed set, and each is accepted only when its evidence verifies against the ledger or the forge at write time:
> - `misderived` — the superseded obligation was written by a derivation (the `plan-resume` or `plan-archive` actor), not by a writer that named it. The evidence is the deriving operation identity, which MUST resolve to that epoch's recorded transition.
> - `disposed` — the superseded target can no longer be fulfilled: its work-item is closed with a resolution other than completion, superseded, or re-parented away from the plan. The evidence is that ledger record.
> - `subsumed` — fulfilling the replacement result necessarily fulfills the superseded one. The evidence is the typed reference both resolve through.
>
> Any other claimed cause MUST be refused: a label, an acknowledgment, approach prose, a repair-child milestone, or elapsed time. So MUST a cause whose evidence does not verify. The replacement MUST inherit the superseded obligation's original deadline and consumed handoff count unchanged. A supersession never consumes a handoff unit and never resets or postpones either limit. Retrying the same operation identity MUST return the recorded event rather than write a second one. A supersession of an already expired obligation remains subject to the expiry rules above. Scenario 211 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 211 — An unmet plan obligation is superseded only by a typed event whose cause verifies, and keeps its original budget

```gherkin
Feature: A wrong obligation can be retired without letting a rename evade expiry
  As the maintainer whose plan pointer was overwritten by a derivation
  I want an evidenced supersession that the ledger can verify
  So that a mis-derived or disposed obligation is replaced while the original budget still binds

  Scenario: A mis-derived obligation is superseded with its deriving operation as evidence
    Given an unmet plan obligation written by the plan-resume actor in a recorded epoch transition
    When set_next_action carries a supersession with cause misderived naming that operation identity and a replacement result
    Then a plan-progress-event of kind supersession is recorded before the pointer changes
    And the replacement result carries the superseded obligation's original deadline and consumed handoff count

  Scenario: A rename without a verified cause is refused
    Given an unmet plan obligation written by an accepted handoff
    When set_next_action carries a supersession with cause misderived
    Then the write is refused because no derivation wrote that obligation
    And the pointer and the obligation are unchanged

  Scenario: A disposed target is superseded with its ledger record as evidence
    Given an unmet plan obligation whose target work-item is closed as superseded
    When append_handoff carries a supersession with cause disposed naming that record
    Then the supersession is recorded and consumes no handoff unit of its own
    And the handoff itself consumes its one unit against the inherited count

  Scenario: A retried supersession records nothing new
    Given a recorded supersession under an operation identity
    When the same operation identity is retried
    Then the recorded event is returned and no second event is written
```
