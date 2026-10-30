---
topic: dod-gate-reference-rule-decision-input
author: claude-opus-5-5
created_at: 2026-10-24T01:34:41Z
---

## Proposal: dod-gate-reference-line-rule-decides-from-scenario-steps

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State in the Definition-of-Done reference-line rule of §"Effective acceptance criteria" (under §"Dispatcher admission, WIP cap, and post-merge acceptance") that whether a `## Scenario NN` heading governs an assertion is decided from that heading's Given/When/Then step lines, never from its title or the judge's own reading, and that the `dod_gate` prompt, the single rubric every taking grades by, MUST state that rule and name that decision input. One unchanged reference line on one unchanged subject then receives the same ruling at every dispatch and at the pre-dispatch judgement. Three new scenarios inside the existing Scenario 141 state the title-versus-steps decision and the cross-taking consistency.

### Motivation

Generalization target: `## Dispatcher admission, WIP cap, and post-merge acceptance`, whose §"Effective acceptance criteria" → "The Definition of Done section" paragraph already states the reference-line rule (a scenario heading whose scenarios state the behaviour must be named; a non-scenario H2 suffices only for an assertion no scenario states), and whose "One rubric, one subject" paragraph makes the `dod_gate` prompt the single rubric every taking grades by. What the ratified text does not say is what the decision input is: whether a scenario "states" the behaviour is left to the judge's reading, so the judge may rule from a scenario's title one time and from its steps the next. Work item bd-ib-46y27z measured exactly that on 2026-10-23 on item bd-ib-kyeor4, whose reference line was `## Self-contained plugin dispatch, ## Dispatcher policy settings` in both of its first two dispatches. In round 1 (run 01M5MKG6W7M1, 14:50Z) dod_gate refused a different bullet and stated that the non-scenario H2 references were valid as written because Scenario 169 states only which image the launch carries. In round 2 (run 01M5MVE4VXG9, 17:05Z), with only the round-1 remedy changed, dod_gate refused the same reference line, demanding that `## Scenario 169` be added. The R265 host pre-dispatch judgement, which grades by the same dod-gate.md prompt, had passed the round-2 text. One unchanged input therefore received opposite verdicts, and each refused round costs a factory slot plus about 40 minutes of pre-launch (bd-ib-6bbcda). Naming the scenario's step lines as the decision input, requiring the rubric to state it, and requiring a quoted step line for any scenario named as governing makes the ruling reproducible across takings and makes a reversal carry new evidence rather than a different reading.

### Proposed Changes

Two coordinated edits. Both MUST land together in a single revision.

**1. `SPECIFICATION/contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → §"Effective acceptance criteria", the paragraph headed **The Definition of Done section.**** The paragraph currently reads, in part:

> Where `scenarios.md` carries a `## Scenario NN — <title>` heading whose scenarios state the behaviour an assertion names, the reference line MUST include that heading: the referenced scenario governs the proof. A reference line naming only a non-scenario H2 while such a scenario exists MUST be reported as a Definition-of-Done finding by the gate, naming the scenario heading that governs the assertion; a non-scenario H2 remains a valid reference for an assertion no scenario states. Scenario 141 in `scenarios.md` exercises this rule.

Immediately after the sentence ending "a non-scenario H2 remains a valid reference for an assertion no scenario states." and before the sentence "Scenario 141 in `scenarios.md` exercises this rule.", insert:

> Whether a scenario heading states the behaviour an assertion names MUST be decided from the Given, When, Then and And step lines of the scenarios under that heading, and never from the heading's title or from the judge's own recollection of the specification. A heading whose title names the behaviour but none of whose steps exercise it does not govern the assertion, and a heading whose steps exercise the behaviour governs it whatever its title says. This decision input MUST be the same for every taking of the Definition-of-Done judgement — the `dod_gate` node, the pre-admission judgement, the pre-dispatch judgement and any host-side preflight — so that one unchanged reference line on one unchanged subject (§"One rubric, one subject" below) receives the same reference-line ruling at every dispatch and at every host taking. Per that paragraph's rule that grading guidance MUST be written into the rubric itself, the `dod_gate` node's prompt file MUST state this reference-line rule once, MUST name the governing scenario's step lines as its decision input, and MUST direct the judge, wherever it reads `scenarios.md` itself rather than taking a returned governing-heading verdict, to quote the step line that states the behaviour when it names a scenario heading as governing an assertion. A taking MUST NOT reverse the ruling on a reference line whose subject digest and rubric digest are unchanged without naming a step line it did not cite before. This sentence leaves unchanged the rule of §"The spec-stated judgement is one shared component" that every taking takes the governing-heading verdict from that component when one was taken.

**2. `SPECIFICATION/scenarios.md` §"Scenario 141 — The referenced scenario governs the proof, and the record names it".** Inside its existing `gherkin` block, immediately after the scenario "A non-scenario reference is valid when no scenario states the behaviour" and before the scenario "The record names the governing scenario", insert:

```gherkin
  Scenario: A scenario whose title names the behaviour but whose steps do not exercise it does not govern the assertion
    Given an item whose assertion names a behaviour that the title of a scenario heading of scenarios.md names
    And no Given, When, Then or And step under that heading exercises that behaviour
    And whose reference line names only a non-scenario heading whose clauses govern the behaviour
    When the dod_gate node evaluates the rendered goal
    Then no scenario-reference finding is reported for that assertion
  Scenario: A scenario whose steps exercise the behaviour governs the assertion whatever its title says
    Given an item whose assertion names a behaviour that a Then step under a scenario heading of scenarios.md states
    And that heading's title does not name the behaviour
    And whose reference line names only a non-scenario heading
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming that scenario heading
    And the finding quotes the step line that states the behaviour
  Scenario: One unchanged reference line receives the same ruling at the pre-dispatch judgement and at every dispatch
    Given an item whose reference line names only non-scenario headings
    And whose subject digest and rubric digest are the same at the pre-dispatch judgement and at two successive dod_gate runs
    When each of those three takings grades the reference line
    Then all three report the same scenario-reference findings for that reference line
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
