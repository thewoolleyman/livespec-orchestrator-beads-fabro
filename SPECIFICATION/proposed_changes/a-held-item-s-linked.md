---
topic: a-held-item-s-linked
author: claude-opus-5-5
created_at: 2026-11-12T04:23:39Z
---

## Proposal: A parallel deposit records the topic it was filed under as its held item's linked topic

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A held spec-change-tier item links to the five-title-word stem the Dispatcher derives, while propose-change files deposits under any topic, so a deposit filed under a longer or different topic never releases its item without a manual relink. This proposal makes the derived stem a prediction only: a new `record-deposit` seam, invoked by the capture, groom and plan front-ends right after a deposit, writes the topic actually filed as the item's linked topic, whatever its word count. The manual relink stays for deposits filed without the seam.

### Motivation

Work item bd-ib-ax3rds.2 (plan bd-ib-ax3rds), reported by the fleet coordinator on 2026-11-12, accepted remedy: the item records the topic its deposit was actually filed under. `proposal_topic_for` caps the derived stem at five words (`_TOPIC_WORD_CAP`), and the hold requires that exact stem's revision record. Measured on 2026-11-12: 349 of 1,322 proposal topics across the governed repositories exceed five words, and 18 are still pending. bd-ib-y2s76v was stranded, linked to the absent `plan-record-artifact-paths-include` while its deposit is the seven-word `plan-record-artifact-paths-include-imported-code`, until the coordinator pressed a relink. The rejected alternative, capping topics in propose-change, would change livespec core, a different repository with a repository-agnostic contract. It would also not help a five-word topic that differs from the title's first five words. In-flight alignment: compatible with bd-ib-jnbcny (surfacing a relink candidate) and bd-ib-flvxx3 (unique derived stems), which this leaves intact. This proposal's own topic is the item's derived stem, so it links without a relink.

### Proposed Changes

**1. The deposit records its own topic (`contracts.md` §"Grooming and slice-size calibration", autonomy-tier bullet).**

Replace the two sentences "The linked topic is first recorded as the stem the Dispatcher derives for the item. When the proposal is filed under a different stem — … — the `relink-spec-tier:<work-item-id>:<topic>` route … MUST replace the item's linked topic with that stem, and the hold MUST thereafter name the replacement topic as the one awaiting ratification." with:

> The linked topic is first recorded as the stem the Dispatcher derives for the item. That stem is a PREDICTION of the deposit's topic, not a constraint on it. When the parallel deposit is filed, the filing session MUST record the topic the deposit was actually filed under through the deposit seam, `dispatcher.py record-deposit --repo <path> --item <work-item-id> --topic <topic>`.
>
> The seam MUST refuse, naming the reason, unless `<spec-root>/proposed_changes/<topic>.md` or a revision record of `<topic>` under `<spec-root>/history/vNNN/proposed_changes/` exists. It MUST also refuse when the item's latest spec-change tier record is not spec-change tier.
>
> On success the seam MUST append one spec-change tier record of stage `deposit` that carries `<topic>` as the linked proposed-change topic and otherwise repeats the latest record. It MUST write no status, and the hold MUST thereafter name `<topic>` as the topic awaiting ratification.
>
> The seam MUST accept every topic the propose-change CLI's canonicalization can produce, whatever its word count. The five-word cap applies only to the derived prediction.
>
> The capture, groom and plan front-ends of this plugin MUST invoke the seam for the held item immediately after a propose-change deposit for it exits 0.
>
> The `relink-spec-tier:<work-item-id>:<topic>` route of §"Per-lane valid operator verb sets" → "Status-independent verbs" remains for a deposit filed without the seam, and for one proposal that generalizes a clause for more than one held item. Either route replaces the item's linked topic, and the hold MUST thereafter name the replacement topic as the one awaiting ratification.

The following sentence ("Every later spec-change tier record of the item … MUST carry the replacement topic forward rather than re-deriving the stem.") is kept unchanged, and it MUST cover a topic recorded by the seam exactly as it covers a relinked one.

**2. Scenario (`scenarios.md`).**

Add the following heading at the end of `scenarios.md`, followed by its gherkin block:

## Scenario: a parallel deposit filed under a longer topic links its held item without a relink

```gherkin
Feature: the topic a deposit is filed under becomes its held item's linked topic
  Scenario: A deposit of more than five words links and later releases its held item
    Given a held spec-change-tier item whose linked topic is the five-word stem the Dispatcher derived for it
    And its parallel deposit is filed through propose-change under a seven-word topic
    When the filing session drives record-deposit for the item naming the seven-word topic
    Then the item's newest spec-change tier record has stage deposit and names the seven-word topic as its linked topic
    And the hold names the seven-word topic as the topic awaiting ratification
    And once that topic's revision record carries decision accept and the re-run judgement returns stated, the next intake or drain pass releases the hold with no human valve
  Scenario: record-deposit refuses a topic with no deposit
    Given a held spec-change-tier item
    When record-deposit is driven naming a topic with no proposed-change file and no revision record
    Then it refuses naming the missing deposit and writes no record
  Scenario: A deposit filed under the derived stem links as before
    Given a held spec-change-tier item whose parallel deposit is filed under exactly the derived stem
    When record-deposit is driven naming that stem
    Then the linked topic is unchanged and the item is held and released exactly as before
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new heading through `resulting_files[]`. `test` MAY be `"TODO"` owned by bd-ib-ax3rds.2, with a non-empty `reason`.
