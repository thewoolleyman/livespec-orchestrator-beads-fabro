---
topic: pre-admission-dod-judgement
author: claude-opus-5-5
created_at: 2026-10-13T09:54:33Z
---

## Proposal: Run the Definition-of-Done judgement before admission and hold an item it would rest at needs-human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The dod_gate judgement is run before an implement-kind item is routed to ready. An item the judgement would rest at needs-human is held out of ready with the verdict and its remedies recorded on it, an item it admits moves as today, a judgement that cannot run leaves routing unchanged with the in-run gate as backstop, and needs-attention lists every held item. The wall's own advisory classification is unchanged. A new Scenario 173 exercises it, and Scenario 140 gains one clarifying step.

### Motivation

Plan hp-factory-failure-follow-ups (epic bd-ib-qieqc6), assertion 2: an item whose Definition of Done carries a references or authoring defect is held out of ready with the judgement's verdict recorded on it, and no run of it ends at dod_gate for that defect. hp measured about 45 of 223 failed ImplementWorkItem runs since 2026-10-09 ending straight from dod_gate on authoring defects the wall classifies as ADVISORY, so each spent a dispatch slot on a defect decidable before dispatch. The implementing item bd-ib-7f66ar was itself rested at needs-human by dod_gate on run 01M4T6VPNZ90 because the ratified clause says such findings MUST NOT withhold ready; this amendment is the spec-change route that verdict prescribes (its remedy (a)). The clause's own rationale, 'because only the gate can judge it', is met by running the gate's judgement at admission.

### Proposed Changes

Amend `contracts.md` §"Definition of Done and Proof of Done" → "Authoring at filing time", add one sentence to Scenario 140, and add Scenario 173. The host-side wall's own classification is unchanged; what changes is that the gate's JUDGEMENT now also runs before admission, which removes the rationale ("only the gate can judge it") for letting a judged defect reach `ready`.

1. In `contracts.md`, immediately after the sentence ending "MUST NOT withhold `ready`, because only the gate can judge it.", insert the following paragraph:

> **Judged before admission.** Before intake routes an implement-kind item to `ready` — from `backlog` or `pending-approval`, whether through intake, the approve valve, or groom — the Dispatcher MUST run the same Definition-of-Done judgement the `dod_gate` node applies (its prompt, against the item's effective criteria, the referenced specification headings and the resolved sandbox capabilities). When that judgement would end a run through the structured needs-human ending, the item MUST NOT be routed to `ready`: it rests where a mechanical finding would hold it, and the verdict, with each remedy, MUST be appended to the item as a ledger comment. When that judgement admits the item, intake MUST route it exactly as it would without the judgement. When the judgement cannot be run (no eligible model, a timeout, or an unparseable verdict), intake MUST record on the item that the pre-admission judgement did not run and why, and MUST route the item as it would without the judgement; the in-run `dod_gate` node remains the backstop, so an unrun judgement never admits anything the gate would not have seen. A wall finding the judgement did not grade stays ADVISORY as above. `needs-attention` MUST list, as hygiene facts, each item held by the pre-admission judgement with its verdict's first remedy; the ready-item advisory hygiene fact below still applies to items the judgement admitted or could not judge. Scenario 173 in `scenarios.md` exercises this paragraph.

2. In `scenarios.md`, Scenario 140's sub-scenario "An advisory finding is recorded and does not withhold ready" MUST gain one final step, `And the wall's advisory finding alone does not withhold ready; the pre-admission judgement of Scenario 173 still applies`. Its heading MUST NOT change.

3. Add a new scenario after Scenario 172:

```gherkin
## Scenario 173 — The Definition-of-Done judgement runs before admission and holds an item it would rest at needs-human

Feature: A judged Definition-of-Done defect is found before a dispatch is spent on it
  Scenario: An item the judgement would rest at needs-human is held out of ready
    Given an implement-kind item whose References line omits the scenario that governs its assertion
    When intake routes the item toward ready
    Then the pre-admission judgement runs against its effective criteria and referenced headings
    And the item is not routed to ready
    And its verdict, with each remedy, is appended to the item as a ledger comment
  Scenario: An item the judgement admits moves to ready as before
    Given an implement-kind item whose Definition of Done the judgement admits
    When intake routes the item toward ready
    Then the item moves to ready exactly as it would without the judgement
  Scenario: A judgement that cannot run does not hold the item
    Given the pre-admission judgement cannot run for an item
    When intake routes the item toward ready
    Then the item is routed as it would be without the judgement
    And a ledger comment records that the pre-admission judgement did not run and why
  Scenario: Held items are surfaced
    Given an item held by the pre-admission judgement
    When needs-attention composes hygiene facts
    Then a hygiene fact names the item and its verdict's first remedy
```

4. `tests/heading-coverage.json` MUST gain an entry for `## Scenario 173 — The Definition-of-Done judgement runs before admission and holds an item it would rest at needs-human` (spec_root `SPECIFICATION`, spec_file `scenarios.md`) with `test` `TODO`, a non-empty `reason` naming its implementing work-item, and `work_item` `bd-ib-7f66ar`.
