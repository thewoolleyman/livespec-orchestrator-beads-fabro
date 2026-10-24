---
topic: governing-heading-omission-advisory
author: claude-opus-5-5
created_at: 2026-10-24T22:54:53Z
---

## Proposal: governing-heading-omission-is-advisory-when-one-named-heading-governs

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A Definition-of-Done reference line that omits a heading the spec-stated judgement returns as governing is REFUSED only when it names no heading the judgement returns as governing any of the item's assertions. When at least one named heading governs, each omitted-heading finding is advisory: it is reported and recorded with the same verbatim remedy, but it does not fail the dod_gate node, hold the item or withhold ready. The rule binds all four takings alike.

### Motivation

The spec-stated judgement names different governing headings for one unchanged subject. Measured 2026-10-24 on this repository's own items: at least seven items were held for 'add heading X' after an earlier taking had passed or named a different heading. Among them, bd-ib-57ss2n, bd-ib-pziqbf and bd-ib-aehdnb each passed the repository preflight and were then refused at the pre-dispatch wall, each costing one factory launch slot for the ~40-minute pre-launch. The overseer seat recorded verdicts that flipped on identical bytes across 07:34Z to 10:35Z (overseer-2x7d5n, overseer-7a6r2e). And a control run on bd-ib-tka3wb on 2026-10-24 returned '## Self-contained plugin dispatch' where the previous taking had returned Scenario 239. A hard refusal on partial omission therefore makes admission non-convergent: each repair invites a new demand. An item whose reference line names a governing heading is already anchored to ratified text, so the residual omission is useful advice, not a reason to stop. Coordinator gitops-fleet-capacity-monitoring ruled this on 2026-10-24 ~23:0xZ under the maintainer's stability-tier direction (epic livespec-dev-tooling-dfixhe), explicitly ruling out a verdict cache and any attempt to make the judge deterministic. This proposal aligns with the pending dod-gate-reference-rule-decision-input proposal, which changes HOW a scenario is decided to govern; this one changes only how hard an omission bites, and the two compose.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Definition-of-Done and Proof-of-Done stages", the `dod_gate` paragraph.** Immediately after the sentence "This reference-coverage finding is a semantic judgement: it MUST NOT be added to the mechanical half the host-side wall runs, and a reference line the wall accepts MAY still carry it." insert:

> A reference-coverage finding is ADVISORY whenever the reference line names at least one heading that the spec-stated judgement (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "The spec-stated judgement is one shared component") returns as governing one of the item's assertions. It MUST still be reported, naming each omitted heading verbatim with the remedy of adding it to the reference line, and it MUST be recorded wherever the taking records its findings. But it MUST NOT fail the node, hold the item or withhold `ready`. Only a reference line that names NO heading the judgement returns as governing any of the item's assertions is refused on reference coverage. Every taking of the Definition-of-Done judgement — the `dod_gate` node, the pre-admission judgement, the pre-dispatch judgement and any host-side preflight — MUST apply this same rule, so the four cannot disagree about whether an omission holds. The judgement can name different governing headings for one unchanged subject, so a refusal on partial omission would hold an item that no single edit reliably clears. Scenario 239 in `scenarios.md` exercises this rule.

**2. `SPECIFICATION/scenarios.md` §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric".** Replace the scenario outline "A reference line missing one of several governing headings is refused by every host taking", together with its Examples table, with these two outlines:

```gherkin
  Scenario Outline: A reference line missing one of several governing headings is reported as advisory by every host taking
    Given an item whose reference line names one of the two scenario headings that state its first assertion's behaviour
    And a non-scenario H2 of contracts.md whose clauses govern its second assertion is not on its reference line
    When the <taking> judgement is taken
    Then it reports the omitted scenario heading and that H2 verbatim, each with the remedy of adding it
    And the item is not held on reference coverage

    Examples:
      | taking               |
      | repository preflight |
      | pre-admission        |
      | pre-dispatch         |

  Scenario Outline: A reference line naming no governing heading is refused by every host taking
    Given an item whose reference line names only headings the spec-stated judgement returns as governing none of its assertions
    When the <taking> judgement is taken
    Then it refuses the item naming each governing heading the judgement returned verbatim, each with the remedy of adding it
    And no factory run is created

    Examples:
      | taking               |
      | repository preflight |
      | pre-admission        |
      | pre-dispatch         |
```

**3. Same scenario block, scenario "A rider that changes the governing heading invalidates the reused governing-heading verdict".** Replace its last step "And a reference line that omits the newly governing heading is refused naming it" with "And a reference line that names none of the newly governing headings is refused naming them".

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
