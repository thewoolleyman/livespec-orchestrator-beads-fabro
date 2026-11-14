---
topic: when-the-dispatch-time-spec
author: claude-opus-5-5
created_at: 2026-11-14T03:04:23Z
---

## Proposal: When the dispatch-time classification does not run, the pre-dispatch wall re-judges once or holds naming the stale record, never presenting it as current

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the dispatch-time spec-change-tier classification of an item does not run and the item's newest tier record was taken against an older spec version, or a different behaviour digest, than the current one, the pre-dispatch wall takes the spec-stated judgement once more before reading the hold. A fresh verdict decides the hold from a record taken against the current version. When that second judgement does not run either, the wall still holds the item, failing closed so that no outage releases items. Its refusal names the did-not-run cause and the version and digest of the stale record it rests on. It never reports the stale record's unratified-topic reason as a verdict against the current spec.

### Motivation

Work item bd-ib-ubcqgo (child of plan factory-run-yield, epic bd-ib-ft26pi, placed there by legacy-coordinator-agent 2026-11-14, ranked high in this plan's revise slot). Measured: at 2026-11-14T02:41:50Z the dispatch-time classification of the priority-1 VPS fix bd-ib-cwuxfi did not run (unparseable verdict). At 02:41:56Z the pre-dispatch wall refused the item as unratified-topic, reading a tier record taken at spec v357 against behaviour digest 1387d39f, while master was at v373 and the digest had changed to 1d1f1f08. The refusal was 16 versions and one asked-for behaviour stale, and read as current. _spec_change_tier_wall classifies, discards the outcome and reads the newest ledger record. Its docstring's reason is real and kept: reading only a fresh outcome would let one provider outage release every held item. The autonomy-tier bullet says the hold 'is a read of the spec history and needs no model, so it MUST fail closed', and says nothing about a hold resting on a record from an older version or digest, so the spec-change-tier judgement graded the item PARTIAL against Scenario 206. Effect on the track metric: a priority-1 fix that could merge was refused, and nothing named why. This makes the refusal re-judge first and otherwise say exactly what it rests on. Measure it as the weekly count of pre-dispatch tier refusals whose standing record's spec version or behaviour digest differs from the current one, with no re-judgement attempted in the same pass; target zero. In-flight alignment: ALIGN with #5068 (a-spec-change-tier-record, bd-ib-bowuak; records name build and rule) and #5080 (a-spec-change-tier-hold, bd-ib-flvxx3; unique derived stems). Both are compatible. Compatible with the sibling a-spec-change-tier-classification, whose did-not-run cause this refusal names.

### Proposed Changes

**1. Re-judge a stale hold once, or name it (`contracts.md` §"Grooming and slice-size calibration", autonomy-tier bullet).** Immediately after the sentence "That hold is a read of the spec history and needs no model, so it MUST fail closed; the pre-dispatch wall MUST refuse a held item with exit code `5` naming the unratified topic, ..." (keeping the rest of that sentence), insert:

> When the dispatch-time classification of an item does not run, and the item's newest spec-change tier record was taken against a specification version or a behaviour digest other than the current ones, the pre-dispatch wall MUST take the spec-stated judgement once more, in the same pass, before it reads the hold. When that judgement returns a verdict, the wall MUST append its tier record and decide the hold from it. When it does not run either, the wall MUST still hold the item, so that no provider outage releases a held item. Its exit-`5` refusal MUST then name the did-not-run cause, the specification version and behaviour digest of the standing record it rests on, and the current ones. It MUST NOT present the standing record's unratified-topic reason as a verdict taken against the current specification. A standing record whose specification version and behaviour digest equal the current ones is read as today, with no second judgement.

**2. Scenario 206 (`scenarios.md`).** Append to Scenario 206:

```gherkin
  Scenario: A stale hold whose classification did not run is re-judged once
    Given a held item whose newest tier record was taken against an older spec version
    And the dispatch-time classification of the item does not run
    When the pre-dispatch wall evaluates the item
    Then the wall takes the spec-stated judgement once more in the same pass
    And when it returns a verdict the hold is decided from a tier record taken against the current spec version

  Scenario: A stale hold that cannot be re-judged stays held and says so
    Given a held item whose newest tier record was taken against an older spec version and behaviour digest
    And neither the dispatch-time classification nor the second judgement runs
    When the pre-dispatch wall evaluates the item
    Then the item is refused with exit code 5
    And the refusal names the did-not-run cause, the standing record's spec version and digest, and the current ones
    And the refusal does not present the unratified topic as a verdict against the current specification

  Scenario: A provider outage releases no held item
    Given many held items whose classifications all fail to run in one pass
    When the pre-dispatch wall evaluates them
    Then every one remains held
```

**3. Heading coverage.** No `## ` heading is added or removed, so `tests/heading-coverage.json` is unchanged.
