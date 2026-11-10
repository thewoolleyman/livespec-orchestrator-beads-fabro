---
topic: a-definition-of-done-edit
author: claude-opus-5-5 (spec-implementation-lockstep session 3fe46ebc)
created_at: 2026-11-10T00:43:40Z
---

## Proposal: A proof-mode-only Definition of Done edit leaves the spec-change tier decision's input unchanged

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Define the asked-for behaviour statement that the spec-change tier decision judges as excluding the Definition of Done's proof-mode partition (the Host-captured and Human-attested sub-headings, their Reason lines, and bullet order). A recorded tier decision is then reused across an edit that only moves a bullet between proof modes, while every real behaviour edit still forces a new judgement.

### Motivation

Work item bd-ib-ajtmgf (priority 1, routed by legacy-coordinator-agent). On livespec-dev-tooling-thhgeg the tier judge read tier none at 2026-11-09T23:27:40Z (spec v173). An edit that only moved bullet 1, word for word, under ### Host-captured changed the behaviour digest, forced a re-judgement at 2026-11-10T00:29:38Z (v174), and that run read spec-change / partial on an unchanged bullet. The hold refused a priority-1 seeded re-dispatch until a human pressed release-spec-tier. Proof mode says how an assertion is proved, not what the item asks for, so the partition should not be part of the judged input. Of the three options weighed, this is the narrowest: it keeps 'a Definition of Done change invalidates the verdict' for every real behaviour edit. Per-bullet re-judgement was rejected because the tier decision is one verdict over the whole statement. A second-candidate agreement before a flip was deferred to plan spec-implementation-lockstep (epic bd-ib-ax3rds).

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "**The spec-stated judgement is one shared component.**", immediately AFTER the sentence ending "has as its input the asked-for behaviour statement, and its spec identity is the clause provenance defined below for a governing-heading verdict: the set of clauses the judgement placed before its model in full, together with every clause the verdict names, each with its heading and body.", insert:

> The asked-for behaviour statement is the item's title, description and acceptance criteria rendered as one statement, EXCEPT that the description's `## Definition of Done` section MUST be rendered without its proof-mode partition: the rendering MUST omit every `### Host-captured` and `### Human-attested` sub-heading together with its `Reason:` line, and MUST render the section's assertion bullets in one canonical order that does not depend on their position or proof mode. Proof mode states how an assertion is proved, not what the item asks for. A Definition of Done edit confined to that partition (moving a bullet word for word between the default `factory_captured` bullets and a `### Host-captured` or `### Human-attested` sub-heading, adding, removing or rewording a `Reason:` line, or reordering bullets) therefore MUST NOT change the spec-change tier decision's input, and a recorded tier decision MUST be reused across it on the same terms as any unchanged input. A change to any bullet's text, to the title, to the `References:` line, or to description text outside the section's bullets changes the input and MUST cause the tier decision to be taken again. This narrowing applies to the spec-change tier decision only; a governing-heading verdict keeps its own input, the assertion's text together with the goal's ledger comments.

2. In the same paragraph, replace the sentence "A change to the item's Definition of Done changes the verdict's input and invalidates it, as a rider does." with: "A change to the item's Definition of Done changes a governing-heading verdict's input and invalidates it, as a rider does; for the spec-change tier decision, a change confined to the proof-mode partition is not a change to its input."

3. In `SPECIFICATION/scenarios.md`, inside `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`, insert the following three Gherkin scenarios immediately AFTER the scenario "A spec revision that changes a judged clause takes the spec-change tier decision again" and BEFORE "The release of a held spec-change-tier item never reuses a verdict across a revision". No H2 heading is added, so `tests/heading-coverage.json` MUST NOT change.

```gherkin
  Scenario: A proof-mode-only Definition of Done edit reuses the spec-change tier decision
    Given an item whose spec-change tier record reads tier none against an unchanged specification revision
    And the only edit to its Definition of Done since the record moves one bullet, word for word, under a `### Host-captured` sub-heading with a new `Reason:` line
    When the item reaches a dispatch path
    Then the recorded tier decision is reused, no model is run, and the item is not held

  Scenario: A reordered Definition of Done reuses the spec-change tier decision
    Given an item whose spec-change tier record was taken against an unchanged specification revision
    And the only edit to its Definition of Done since the record reorders its bullets
    When the item reaches a dispatch path
    Then the recorded tier decision is reused and no model is run

  Scenario: A reworded Definition of Done bullet takes the spec-change tier decision again
    Given an item whose spec-change tier record was taken against an unchanged specification revision
    And one word of one Definition of Done bullet has changed since the record
    When the item reaches a dispatch path
    Then the tier decision is taken again
```

