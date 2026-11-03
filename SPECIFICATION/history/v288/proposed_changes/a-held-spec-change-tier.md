---
topic: a-held-spec-change-tier
author: claude-opus-5-5
created_at: 2026-11-03T17:39:13Z
---

## Proposal: A held spec-change-tier item can be relinked to the proposed-change topic actually filed for it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a status-independent `relink-spec-tier:<work-item-id>:<topic>` route that replaces a held spec-change-tier item's linked proposed-change topic with the stem of the proposal actually filed for it, refuses for an item that is not held and for a stem that names no proposed change, records a durable ledger comment carrying the actor and both topics, and is carried forward by every later tier record. The hold then waits on the replacement topic, so the ratification release the autonomy-tier bullet already states reaches the item with no human valve.

### Motivation

Work-item bd-ib-6is4z7 (plan spec-implementation-lockstep, epic bd-ib-ax3rds), queued there as defect (a) on 2026-11-02 and re-verified on master 091e46ee9 on 2026-11-03. The autonomy-tier bullet requires a held item to carry a linked proposed-change topic and releases the hold once that topic's revision record carries accept or modify and the re-run judgement returns stated. But the specification states no route that records or replaces the linked topic, and the implementation only ever writes the stem it derives from the item's title (decide_spec_change_tier records proposal_topic_for(item), the first five title words; every later record carries that stem forward). When the proposal is filed under any other stem, the hold reads unratified-topic for ever: a filer canonicalizes the topic differently, or one proposal generalizes an existing clause for two or more held items, where only one item's derived stem can match. Today the only ways out are the human release-spec-tier attestation or a hand-run apply_intake_dor re-judgement, and neither is the ratification release the clause names. Relinking releases nothing by itself: ratification of the replacement topic and a stated re-run judgement are still both required, so the route needs no human-only restriction.

### Proposed Changes

Two edits, one in each target file. Every other sentence of each edited paragraph is kept unchanged.

**1. `SPECIFICATION/contracts.md`, §"The four maintainer touchpoints", touchpoint 1, the bullet "An autonomy tier is assigned".**

Immediately after the sentence

> A spec-change-tier item MUST carry a linked proposed-change topic, filed beside it through `/livespec:propose-change` as the parallel deposit, and the judgement MUST name an existing heading to generalize in preference to a new clause whenever one exists.

insert

> The linked topic is first recorded as the stem the Dispatcher derives for the item. When the proposal is filed under a different stem — the filer canonicalized it differently, or one proposal generalizes a clause for more than one held item — the `relink-spec-tier:<work-item-id>:<topic>` route of §"Per-lane valid operator verb sets" → "Status-independent verbs" MUST replace the item's linked topic with that stem, and the hold MUST thereafter name the replacement topic as the one awaiting ratification. Every later spec-change tier record of the item, at groom, on a dispatch path or on an intake or drain pass, MUST carry the replacement topic forward rather than re-deriving the stem.

**2. `SPECIFICATION/contracts.md`, §"Per-lane valid operator verb sets" → "Status-independent verbs".**

After the `close-duplicate:<work-item-id>:<successor-id>` paragraph, add the paragraph

> `relink-spec-tier:<work-item-id>:<topic>` is valid in every lane except `done`, and is likewise not enumerated per row. It is a field-setter on the spec-change-tier hold, not a transition: it replaces the held item's linked proposed-change topic with `<topic>` and MUST NOT write a status, release the hold, or change any other item. Because the hold is still released only by the ratification of the replacement topic together with a `stated` re-run judgement, the route MAY be driven by a human or by an agent session. It MUST refuse, naming the reason and writing nothing, when the item carries no spec-change-tier hold, when `<topic>` is not a canonical topic stem, and when `<topic>` names no proposed change, either a pending `<spec-root>/proposed_changes/<topic>.md` or a revision record under `<spec-root>/history/vNNN/proposed_changes/`. On success it MUST record a durable ledger comment on the item carrying the actor, the previous linked topic and the replacement topic, and it MUST append the replacement as a spec-change tier record whose linked topic is `<topic>` and whose verdict, generalization target and clause provenance are the standing record's, so the hold read, the pre-dispatch wall's exit-`5` refusal and the next intake or drain pass all name the replacement topic. Relinking an item whose replacement topic is already ratified MUST NOT itself release the hold; the next intake or drain pass re-runs the judgement against the ratified specification and releases it exactly as the autonomy-tier bullet states.

**3. `SPECIFICATION/scenarios.md`, §"Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification".**

Append the following scenarios to the end of the section's gherkin block, after the scenario "An attestation survives an unrelated revision and a rejected proposal, and voids on a changed clause or input". No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no change.

```gherkin
  Scenario: A held item is relinked to the proposal actually filed for it and released when that proposal ratifies
    Given a held spec-change-tier item whose linked topic is the stem the Dispatcher derived for it
    And its proposal was filed under a different topic stem
    When relink-spec-tier is driven for the item naming the filed stem
    Then the hold names the filed stem as the topic awaiting ratification
    And a durable ledger comment on the item records the actor, the previous topic and the replacement topic
    And once the filed topic's revision record carries decision accept and the re-run judgement returns stated, the next intake or drain pass releases the hold with no human valve

  Scenario: Relinking is refused for an item that is not held or a topic that names no proposal
    Given an item that carries no spec-change-tier hold
    When relink-spec-tier is driven for it
    Then the route refuses naming the reason and writes nothing
    And when relink-spec-tier is driven for a held item naming a stem with no proposed change under the spec root's proposed_changes directory or its history, it refuses naming the unknown topic and the item keeps its linked topic
```
