---
topic: the-approve-valve-refuses-an
author: claude-opus-5-5
created_at: 2026-11-12T14:40:00Z
---

## Proposal: The approve valve reads the spec-change hold, and a held item found at ready is withdrawn to backlog

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The autonomy-tier bullet requires a spec-change-tier item to be "held out of `ready`" and names only the pre-dispatch wall as the place that refuses it. It does not say the `approve` valve reads the hold, and it does not say what happens to a held item that is already at `ready`. This proposal makes `approve` refuse an unratified held item before any model call, and keeps a ratified one awaiting its re-judgement working through `approve`. It also makes an intake or drain pass withdraw an unratified held item it finds at `ready` to `backlog`, so no held item rests at `ready` where every launch is refused.

### Motivation

Work item bd-ib-bomy33 (plan bd-ib-ax3rds), filed on legacy-coordinator-agent's order (session e61db277, R301, 2026-11-07). It is held at spec-change tier for this linked topic: verdict partial, generalization target `## Grooming and slice-size calibration`. The topic is the item's recorded linked stem, so the hold links without a relink.

Measured by radar-and-deterministic-admission on 2026-11-07 at 20:03Z, through build 1895a0ddbe37 over 11 tenants:
- 42 `ready` items were held, and 31 of them had no proposal for their topic on master (livespec-dev-tooling 15, this tenant 16). That is a floor, because 122 `ready` items had no tier record.
- `commands/_drive_approve_valve.py` runs the factory-size decision and the two Definition-of-Done walls, with no spec-change read. So a held item enters `ready` and is then refused at the pre-dispatch wall with exit code `5` on every launch, indefinitely.
- bd-ib-3asaxk reached `ready` by another path and rests there; a launcher gave up on the refusal on 2026-11-04 at 16:11Z.
- bomy33 itself has sat at `ready` while held. The dispatcher's launcher ended "before listing" on that same permanent refusal on 2026-11-12 at 06:06Z, and did not re-ticket.

Design choices, stated for the grade:
- **One hold rule.** Approve and the pass read the same hold the pre-dispatch wall reads. Nothing here adds a second rule.
- **Cheap first.** The unratified refusal is a read of the spec history, so it comes before the Definition-of-Done judgement and costs no model call.
- **The ratified arm is load-bearing.** A manual-admission item released by ratification rests at `pending-approval`, and the drain re-judges only `ready` rows. Refusing it outright would strand it. On 2026-11-07 the coordinator relinked homelab hl-jq6ov3 onto a ratified topic and pressed approve, which is the press this arm keeps working.
- **Ratified items at `ready` stay.** `relink-spec-tier` onto a ratified topic deliberately leaves the item at `ready` for the pass's re-judgement; six items were relinked that way on 2026-11-07. Moving them to `backlog` would undo the route the specification prescribes.
- **Withdraw, never rest at `pending-approval`.** `pending-approval` is never a move target, so the withdrawal goes to `backlog` through the existing journaled `move→backlog`, and re-entry is through intake routing.

In-flight alignment, all `align`:
- #5019, approve-refuses-on-a-proof (pending), extends the Definition-of-Done judgement to every route into `ready`. This proposal places the hold read BEFORE that judgement and leaves its rubric unchanged.
- #5036, #5037 and #5042, and the pending the-spec-change-tier-judgement, change how the judgement is taken, not where approve reads the hold.
- raise-a-ready-item-refused concerns the attended-host refusal, a different refusal.

Fleet scope: the valve and the passes are the orchestrator Dispatcher's, so every beads tenant inherits the change through the plugin. livespec-orchestrator-git-jsonl has no `approve` path, so it is unaffected.

Grade fixes applied (legacy-coordinator-agent, session 959b2f8b): a hold released by a non-void `release-spec-tier` attestation is exempt from both the refusal and the withdrawal, because that valve is the human's only route through. A pass that cannot read the spec history withdraws nothing. The no-linked-topic case has its own scenario. The hold reasons this text describes are the ones the Dispatcher names `no-linked-topic`, `unratified-topic` and `awaiting-rejudgement`.

### Proposed Changes

**1. The approve valve and the passes read the hold (`contracts.md` §"Grooming and slice-size calibration", the "An autonomy tier is assigned" bullet).** After the sentence ending "the pre-dispatch wall MUST refuse a held item with exit code `5` naming the unratified topic," and before "and once both conditions hold", the clause continues as below. The current sentence is split, so the new sentences stand on their own and the "once both conditions hold" text keeps its meaning.

> Every route into `ready` MUST read that same hold, and none may adopt a second hold rule. The `approve` valve MUST read it before it takes the Definition-of-Done judgement. It MUST refuse a `pending-approval` item that is held because the item has no linked topic, or because its linked topic has no revision record with decision `accept` or `modify`. The refusal names the linked topic and the reason, takes no Definition-of-Done judgement, makes no model call, and leaves the item at `pending-approval`. For a `pending-approval` item whose linked topic carries such a revision record but whose judgement has not yet been re-run against the ratified specification, `approve` MUST first take the item's spec-change tier classification again against the ratified specification. It then routes the item as the release below would when no hold stands afterwards, and otherwise refuses, naming the topic and the reason. An item whose newest spec-change tier record reads tier none, or that carries no such record, is approved exactly as it would be without this sentence. When the spec history cannot be read, `approve` MUST refuse an item whose newest spec-change tier record reads tier spec-change, and MUST NOT move it to `ready`. An intake or drain pass that reaches a `ready` item held because it has no linked topic, or because its linked topic has no revision record with decision `accept` or `modify`, MUST withdraw it to `backlog` through the journaled `move→backlog`. It records a ledger comment naming the linked topic and the reason. A `ready` item whose linked topic carries such a revision record, and that is due its re-run judgement, stays at `ready`, and the pass takes that judgement rather than withdrawing it. When the spec history cannot be read, an intake or drain pass MUST leave every `ready` item where it is, withdraw nothing, and record on the item that the hold could not be read. An item whose hold a `release-spec-tier` attestation released, while that attestation is not void, is NOT held for this sentence: `approve` takes it as it would any other item, and no pass withdraws it. An item withdrawn this way re-enters only through intake routing.

The existing text then resumes with "Once both conditions hold the item is no longer spec-change tier…", unchanged in substance. A withdrawn item whose topic later ratifies, and whose re-run judgement returns `stated`, is therefore routed by its effective `admission_policy` with no human valve, exactly as that text already says.

**2. The lane-verb row (`contracts.md`, the per-lane verb table, row `pending-approval`).** Change the `approve` cell's parenthetical from

> approve (the single door toward `ready`; for an effective-auto item it re-runs the intake Definition-of-Done check first)

to

> approve (the single door toward `ready`; it refuses a spec-change-tier-held item per §"Grooming and slice-size calibration"; for an effective-auto item it re-runs the intake Definition-of-Done check first)

**3. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 356 are claimed by pending proposals.

## Scenario 357 — The approve valve refuses a spec-change-tier-held item, and a held item found at ready is withdrawn to backlog

```gherkin
Feature: no spec-change-tier-held item waits at ready unable to launch
  Scenario: approve refuses an item held for an unratified topic, before any model call
    Given a pending-approval item whose newest spec-change tier record reads tier spec-change
    And its linked topic has no revision record with decision accept or modify
    When approve is driven for the item
    Then approve refuses, naming the linked topic and the hold reason
    And no Definition-of-Done judgement is taken and no model is called
    And the item stays at pending-approval

  Scenario: approve refuses an item held with no linked topic
    Given a pending-approval item whose newest spec-change tier record reads tier spec-change
    And the item carries no linked proposed-change topic
    When approve is driven for the item
    Then approve refuses, naming the missing topic as the hold reason
    And no model is called and the item stays at pending-approval

  Scenario: approve takes an item whose hold a human attestation released
    Given a pending-approval spec-change-tier item whose linked topic is unratified
    And a release-spec-tier attestation released its hold and is not void
    When approve is driven for the item
    Then approve takes the item as it would any other item
    And no intake or drain pass later withdraws it to backlog

  Scenario: approve re-judges an item whose linked topic has ratified
    Given a pending-approval item whose linked topic carries a revision record with decision accept
    And the item's judgement has not been re-run against the ratified specification
    When approve is driven for the item
    Then the spec-change tier classification is taken again against the ratified specification
    And the item is admitted when no hold stands afterwards
    And otherwise approve refuses, naming the topic and the reason

  Scenario: approve is unchanged for an item that is not spec-change tier
    Given a pending-approval item whose newest spec-change tier record reads tier none, or that carries no such record
    When approve is driven for the item
    Then it is admitted or refused exactly as it was before this scenario

  Scenario: approve fails closed when the spec history cannot be read
    Given a pending-approval item whose newest spec-change tier record reads tier spec-change
    And the governed spec history cannot be read
    When approve is driven for the item
    Then approve refuses and the item does not move to ready

  Scenario: a pass withdraws an unratified held item from ready
    Given a ready item held because its linked topic has no revision record with decision accept or modify
    When an intake or drain pass reaches the item
    Then the item is moved to backlog through the journaled move
    And a ledger comment on the item names the linked topic and the reason

  Scenario: a pass that cannot read the spec history withdraws nothing
    Given a ready item whose newest spec-change tier record reads tier spec-change
    And the governed spec history cannot be read
    When an intake or drain pass reaches the item
    Then the item stays at ready
    And the item records that its hold could not be read

  Scenario: a pass leaves a ratified item due its re-judgement at ready
    Given a ready item whose linked topic carries a revision record with decision accept
    And the item is due its re-run judgement
    When an intake or drain pass reaches the item
    Then the item stays at ready and the pass re-judges it

  Scenario: a withdrawn item whose topic ratifies is routed with no human valve
    Given an item withdrawn to backlog this way
    And its linked topic later carries a revision record with decision accept
    And the re-run judgement returns stated
    When the next intake or drain pass reaches the item
    Then the item routes as its effective admission_policy decides, with no human valve
```

Revise co-edit: the new `## Scenario` heading needs a `tests/heading-coverage.json` row, carried through `resulting_files[]` as `../tests/heading-coverage.json` or edited in the revise commit. The row is `"TODO"` with a reason naming bd-ib-bomy33 as the implementing item, plus a debt-register entry.
