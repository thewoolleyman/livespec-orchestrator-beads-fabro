---
topic: the-filing-display-recognises-only
author: claude-opus-5-5
created_at: 2026-11-12T06:50:39Z
---

## Proposal: A scenario heading is either form, numbered or unnumbered

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Definition of Done reference rules name a governing scenario only as a `## Scenario NN — <title>` heading, so the filing display treats a reference to an unnumbered `## Scenario: <title>` heading as naming no scenario, and never offers one as a candidate. This proposal defines a scenario heading as an H2 of scenarios.md whose title begins `Scenario`, numbered or unnumbered, and requires every surface that recognises scenario references to treat both alike.

### Motivation

Work item bd-ib-yryub7 (plan bd-ib-ax3rds), routed by the fleet coordinator on 2026-11-12 after approve:bd-ib-y2s76v. y2s76v's reference to v359's "## Scenario: a plan record that reaches a released component only through imported code is judged by tree identity" drew the advisory "the reference line names no scenario heading" (06:34:37Z), and the reference was deleted to get the item through. Measured on build 58fb211b056e, the mechanical reference wall resolves the unnumbered heading; the advisory path recognises a scenario only by the prefix `Scenario ` (with a trailing space), which matches the spec's numbered-only wording. Fleet scope: on origin/master, scenarios.md carries the unnumbered form exclusively in nine repositories (livespec-overseer 552, livespec-dev-tooling 379, livespec-runtime 56, resume 42, livespec-driver-codex 40, livespec-driver-claude 26, dolt-server 25, livespec-driver-pi 21, hetzner-xubuntu-info 18). In those repositories the scenario advisory never fires. This repository mixes 14 unnumbered with 330 numbered, git-jsonl mixes 1 with 6, and only the console is numbered-only. The alternative, numbering every heading through revise or doctor, would renumber 1,174 headings across 11 repositories, plus every heading-coverage row and reference that names them, so it is rejected. In-flight alignment: none of the open spec PRs (#5005, #5009, #5010) touches this wording (align). Sibling bd-ib-rla7ol widens the same recognition for `## Contributor Scenario <letter> -- ...` headings and is compatible with it. This proposal's topic is the item's derived stem, so it links without a relink.

### Proposed Changes

**1. One definition of a scenario heading (`contracts.md`).**

In §"Dispatcher admission, WIP cap, and post-merge acceptance", in "The Definition of Done section" paragraph, replace "a `## Scenario NN — <title>` heading of `scenarios.md`" in the reference-line grammar with:

> a SCENARIO HEADING of `scenarios.md`: an H2 whose title begins `Scenario`, in either form the family's specification trees use, numbered (`## Scenario NN — <title>`) or unnumbered (`## Scenario: <title>`)

In the same paragraph, the sentence "Where `scenarios.md` carries a `## Scenario NN — <title>` heading whose scenarios state the behaviour an assertion names, the reference line MUST include that heading" MUST read "Where `scenarios.md` carries a scenario heading whose scenarios state the behaviour an assertion names, …". The rest of the sentence is unchanged.

In §"Self-contained plugin dispatch", the reference-line clause "each `## Scenario NN — <title>` heading of `scenarios.md` that states behaviour …" MUST read "each scenario heading of `scenarios.md`, as §"Dispatcher admission, WIP cap, and post-merge acceptance" defines it, that states behaviour …".

Add one sentence after the definition:

> Every surface that decides whether a reference names a scenario, or that offers a scenario heading as the candidate governing an assertion, MUST treat both forms alike. The filing display, the host-side wall and the `dod_gate` node's rubric are such surfaces. A reference to an unnumbered scenario heading MUST NOT be reported as naming no scenario heading.

**2. Scenario (`scenarios.md`).**

Add the following heading at the end of `scenarios.md`, followed by its gherkin block:

## Scenario: an unnumbered scenario heading is a scenario reference

```gherkin
Feature: both scenario heading forms govern an assertion alike
  Scenario: A reference to an unnumbered scenario heading counts as naming a scenario
    Given scenarios.md carries the heading "## Scenario: <title>" whose steps state an item's asserted behaviour
    And the item's reference line names that heading
    When the filing display reports the item's Definition-of-Done findings
    Then no finding says the reference line names no scenario heading
  Scenario: An unnumbered scenario heading is offered as the governing candidate
    Given scenarios.md carries the heading "## Scenario: <title>" whose steps state an item's asserted behaviour
    And the item's reference line names only a non-scenario H2
    When the filing display reports the item's Definition-of-Done findings
    Then the advisory finding names "Scenario: <title>" as the scenario that governs the assertion
  Scenario: A numbered scenario heading behaves as before
    Given the item's reference line names a "## Scenario NN — <title>" heading whose steps state its asserted behaviour
    When the filing display reports the item's Definition-of-Done findings
    Then it reports exactly what it reported before this change
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new heading through `resulting_files[]`. `test` MAY be `"TODO"` owned by bd-ib-yryub7, with a non-empty `reason`.
