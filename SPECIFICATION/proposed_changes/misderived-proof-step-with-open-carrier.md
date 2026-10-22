---
topic: misderived-proof-step-with-open-carrier
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-22T05:47:42Z
---

## Proposal: A plan-level step derived while a carrier was open is misderived

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen the closed `misderived` cause of an evidenced causal supersession with a second qualifying case. A proof, review or archive obligation that a derivation wrote while a work-item carrier named by the epic's latest carrier-map scope event was not closed could never have been fulfilled honestly at that moment, so it is misderived. It may be superseded by a typed event whose evidence is the deriving operation identity plus that carrier's ledger record, and the replacement keeps the original deadline and consumed handoff count. Two scenarios are added under the existing Scenario 211 heading, whose text is unchanged.

### Motivation

Measured 2026-10-22 on plan epic bd-ib-fyozyd (plan petri-factory-on-gmktec), build v0.230.2. When the awaited carrier livespec-dev-tooling-knd3s7 closed, resume_directive persisted a derived `proof:capture:bd-ib-fyozyd` obligation while nine ordinal-6 carriers in other tenants were still open, so no honest plan Proof of Done could be captured. Every later re-aim was refused: an await on the open carrier livespec-driver-codex-extptf was refused with 'cannot be renamed ... without evidenced causal supersession', because the only `misderived` case is an impl step whose target carries a factory-safety label, and neither `disposed` nor `subsumed` applies. The epic had to fall back to a human pointer, although no human decision is owed. Work-item bd-ib-evrynu carries the derivation fix; its assertion 5 needs this clause, and its launch-time preflight correctly refused it as ungradeable against the current Scenario 211. Coordinator rulings R562 and R202 direct this carve-out.

### Proposed Changes

In `contracts.md` §"Required result, budget and progress epoch", the `misderived` bullet of the closed cause set MUST be replaced by a bullet carrying two qualifying cases. The causes remain a closed set, and every other rule of the paragraph (unsatisfied replacement, inherited deadline and handoff count, no handoff unit consumed, idempotent retry, expiry still applies) MUST stay unchanged.

```diff
-- `misderived` — the superseded obligation was written by a derivation (the `plan-resume` or `plan-archive` actor), not by a writer that named it, AND it names an `impl` step whose target work-item already carried a `factory-safety` label when that derivation was recorded, so the step could never have been factory-dispatched. The evidence is the deriving operation identity, which MUST resolve to that epoch's recorded transition, and the target's recorded ledger history showing the label applied at or before that transition's recorded time. A label applied after the derivation does not qualify, and a derived obligation whose step its target could take when it was derived is not misderived, however it was written or whatever its target carries now.
+- `misderived` — the superseded obligation was written by a derivation (the `plan-resume` or `plan-archive` actor), not by a writer that named it, AND one of these held when that derivation was recorded:
+  - it names an `impl` step whose target work-item already carried a `factory-safety` label, so the step could never have been factory-dispatched; or
+  - it names a plan-level step (`proof`, `review` or `archive`) while a work-item carrier named by the epic's latest carrier-map scope event was not closed, so the step could not honestly be taken.
+  The evidence is the deriving operation identity, which MUST resolve to that epoch's recorded transition, together with the ledger record that establishes the case: for the first, the target's recorded history showing the label applied at or before that transition's recorded time; for the second, the carrier's recorded status history showing it not closed at that transition's recorded time. A label applied after the derivation does not qualify, and neither does a carrier that was closed when the derivation was recorded. A derived obligation whose step could legitimately be taken when it was derived is not misderived, however it was written or whatever its target or carriers show now.
```

In `scenarios.md`, under the existing heading `## Scenario 211 — An unmet plan obligation is superseded only by a typed event whose cause verifies, and keeps its original budget` (heading text unchanged, so `tests/heading-coverage.json` needs no edit), these two scenarios MUST be added after `A label applied after the derivation does not make it misderived`:

```gherkin
  Scenario: A plan-level step derived while a carrier was open is superseded by an await on that carrier
    Given an unmet plan obligation written by the plan-resume actor in a recorded epoch transition
    And it names a proof step while a work-item carrier named by the epic's latest carrier-map scope event was not closed at that transition
    When set_next_action carries a supersession with cause misderived naming that operation identity and an await on that carrier as the replacement result
    Then a plan-progress-event of kind supersession is recorded before the pointer changes
    And the replacement result carries the superseded obligation's original deadline and consumed handoff count

  Scenario: A plan-level step derived after its carriers closed is not misderived
    Given an unmet plan obligation written by the plan-resume actor naming a proof step
    And every work-item carrier named by the epic's latest carrier-map scope event was closed when that transition was recorded
    When set_next_action carries a supersession with cause misderived
    Then the write is refused and the obligation is unchanged
```
