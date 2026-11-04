---
topic: filing-surfaces-duplicate-candidates
author: claude-opus-5-5
created_at: 2026-10-25T01:22:24Z
---

## Proposal: Every filing front-end surfaces candidate duplicates before the filing is confirmed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The paragraph "Authoring at filing time" already lists what every filing front-end (`capture-work-item`, `capture-impl-gaps`, `groom`, and the `plan` front-end when it routes a child) MUST display before a filing is confirmed. This proposal adds one more entry to that display: the open work-items of the same tenant that look like the item being filed, ranked by a deterministic vocabulary-overlap measure, with the searched population stated so that an empty answer is never mistaken for clearance. The display advises and never refuses, exactly like the Definition-of-Done findings beside it.

### Motivation

Work-item bd-ib-igeoe6 (feature, no owning plan; R1 bd-ib-j6uvkj batch 10 routed it here as needing a linked proposal). Measured 2026-08-21 in the livespec-overseer tenant: overseer-hgq4wi.26 (05:46:46Z) and overseer-bnutz7 (07:01:55Z) described the same defect under the same parent epic, both open and separately dispatchable, and only a later grooming sweep caught it. Today no clause requires the filing path to look for duplicates, and the filing path is the one point every filing passes through with the item's title and description already in hand. Exact-title matching would not have fired on that instance, because the two titles share no distinctive phrase; their descriptions share substantial vocabulary and their parent. The item also names the two failure directions a surfacer must control: one that reports nothing on a genuine duplicate reads as clearance, and one that blocks on superficial similarity trains filers to dismiss it unread. The generalization target is the existing "Authoring at filing time" display duty, so no new section is added.

### Proposed Changes

Two edits, landing in one revision. No `## ` heading is added, renamed or removed in `contracts.md`; one scenario is added to `scenarios.md`, so `tests/heading-coverage.json` gains one entry for it (`test` MAY be `"TODO"` with a reason).

**1. `contracts.md`, the paragraph that begins "**Authoring at filing time.**".** After the sentence that ends "...and every Definition-of-Done finding the host-side wall can detect;" and before "when the filer declines the section it MUST display `definition-of-done: missing`", the display duty gains a duplicate-candidate entry. Insert, as new sentences immediately after the paragraph's sentence "Filing stays consent-gated and a front-end MUST NOT refuse on a finding.":

```
Each such front-end MUST also display, before the filing is confirmed,
the item's DUPLICATE CANDIDATES: the work-items of the same tenant whose
status is not `closed` and whose vocabulary overlaps the item being
filed. The *words* of a text are the maximal runs of the characters `a`-`z`
and `0`-`9` in it after it is lowercased. The *significant terms* of an
item are the distinct words of at least four characters in its title and
description, excluding every word listed in the stop-word file
`.claude-plugin/data/duplicate-candidate-stop-words.txt`, which this
plugin commits as UTF-8 text holding one lowercase word per line; every
filing front-end MUST read that one file, and the display MUST show the
lowercase hexadecimal SHA-256 digest of its bytes; the *overlap* of a candidate is the number of the filing's
significant terms the candidate also carries, divided by the number of
significant terms the filing carries, so a candidate that carries no
significant term has an overlap of 0. An item QUALIFIES as a candidate when
its overlap is at least 0.2, or when it sits under the same parent epic
as the filing and its overlap is at least 0.1. The qualifying items are
ordered by these keys in turn: same-parent items before all others, then
descending overlap, then ascending work-item id, so the order is fully
determined. The display MUST list the first five qualifying items in
that order and, when more than five qualify, MUST state how many more
qualified; each entry
shows its id, title, status and the filing's significant terms it shares,
at most five of them, in descending order of how often they occur in the
filing's title and description counted together, and then
alphabetically. When the filing itself has no
significant terms, the overlap is not computed and the display MUST read
`duplicate-candidates: not computed` with that reason, and MUST NOT read
`none`. The computation MUST be deterministic
and MUST NOT call a language model. When no candidate qualifies, the
display MUST read `duplicate-candidates: none` followed by the number of
non-closed items it compared, so that the scope of the negative is visible;
when the tenant's non-closed items cannot be read, it MUST read
`duplicate-candidates: unobservable` with the cause, and MUST NOT read
`none`. Candidates are ADVISORY: the front-end MUST NOT refuse or delay
the filing on them, and they MUST NOT withhold `ready`. When the filer
adopts a candidate instead of filing, the front-end MUST file nothing
and MUST offer to add the new item's evidence to the adopted candidate
as a ledger comment. When the filer confirms the filing with candidates
displayed, the filed item MUST carry one ledger comment naming each
displayed candidate's id, so a later grooming pass can find the pair.
```

**2. `scenarios.md`.** Add one scenario after the highest-numbered scenario, numbered by the revise pass:

```gherkin
Feature: A filing shows the non-closed items it may duplicate
  Scenario: A same-parent item with overlapping vocabulary is displayed
    Given a non-closed item under epic E whose description shares a quarter of a new filing's significant terms
    And the new filing names E as its parent and shares no phrase with that item's title
    When the capture front-end displays the filing before confirmation
    Then the display lists that item among its duplicate candidates with its id, title, status and shared terms
    And the filing is not refused

  Scenario: No candidate is reported with its scope
    Given a tenant with 40 non-closed items none of which overlaps a new filing by 0.1 or more
    When the capture front-end displays the filing
    Then the display reads duplicate-candidates none and names the 40 non-closed items compared

  Scenario: A filing with no significant terms is not reported as clear
    Given a filing whose title and description contain no word of four or more characters outside the stop-word list
    When the capture front-end displays the filing
    Then the display reads duplicate-candidates not computed with that reason
    And it does not read duplicate-candidates none

  Scenario: An unreadable ledger is not reported as no candidates
    Given the tenant's non-closed items cannot be read
    When the capture front-end displays the filing
    Then the display reads duplicate-candidates unobservable with the cause
    And it does not read duplicate-candidates none

  Scenario: Confirming a filing with candidates records them
    Given a filing whose display listed two duplicate candidates
    When the filer confirms the filing
    Then the filed item carries one ledger comment naming both candidate ids
    And intake does not withhold ready on them
```
