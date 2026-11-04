---
topic: spec-stated-judgement-and-spec-change-tier
author: claude-fable-5-1:spec-implementation-lockstep
created_at: 2026-10-20T01:08:12Z
---

## Proposal: The spec-stated judgement decides the spec-change tier, and a feature waits for its linked proposal's ratification before dispatch

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

One judgement, imported from the livespec-runtime module livespec_runtime.spec_stated, answers two questions the Dispatcher asks today by hand: is this behaviour stated by the ratified spec, and by which heading; and is this item a feature, a bug, a chore or non-functional. The Definition-of-Done judgement that already runs before admission, before dispatch and in the dod_gate node takes its governing-heading verdict from that component and keeps every other duty. The Definition-of-Ready autonomy tier is decided by the same judgement: a feature whose asked-for behaviour is partial or unstated is spec-change tier, carries a linked proposed-change topic filed beside it, and is held out of ready, mechanically, until that topic's revision record is accept or modify and the judgement returns stated against the ratified spec; bugs, chores and non-functional items are exempt; the judgement names an existing heading to generalize in preference to a new clause; the tier is never read off spec_commitment_hint.

### Motivation

Plan spec-implementation-lockstep (epic bd-ib-ax3rds), Definition of Done assertions 1, 2, 3 and 6, from the maintainer's 2026-10-19 rulings: new behaviour gets new spec, bugs and chores and non-functional work have leeway, rejection must not become overspecification, and the spec is generalized rather than expanded. Measured 2026-10-19 in this repository: 11 of the 14 real dod_gate refusals on record were citation refusals, split between behaviour the spec did not state at all (bd-ib-fd26sc, bd-ib-nsrgxl, bd-ib-7rnipp) and a filer citing a clause that does not govern the item (six items); 1,190 of 1,504 items ever filed are origin:freeform, and nothing at filing asks whether the spec states the behaviour. The audit of 304 open items classified 88 UNGOVERNED and 54 PARTIAL. The spec-change tier has no ratified classifier, and its code stand-in reads spec_commitment_hint, which marks an implementation follow-up to an already ratified change (bd-ib-yykjko). The independent review of the plan's scoping (research note 004) required the ratification read to be a mechanical fact rather than a proposal's presence, the classification to cover every implement-kind item rather than the stored type, and the judgement to be a component of the full Definition-of-Done judgement rather than its replacement.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance" → "Effective acceptance criteria" → "Authoring at filing time", insert the following paragraph immediately BEFORE the paragraph that begins "**Judged before admission.**":

> **The spec-stated judgement is one shared component.** The Dispatcher MUST obtain two verdicts from the `livespec_runtime.spec_stated` module of the livespec-runtime release this plugin vendors, and from nowhere else: for a behaviour statement, whether the ratified specification states it — `stated`, naming each governing H2 heading verbatim; `partial` or `unstated`, naming the existing heading whose generalization would state it, or none — and for a work-item, whether it is a `feature`, a `bug`, a `chore` or `non_functional`, the stored type being evidence rather than the answer. The module defines the prompt, the inputs and the verdict schema and invokes no model itself; the Dispatcher supplies the model runner through the module's injected callable, so the judgement is defined once for every orchestrator. The Definition-of-Done judgement named in the two paragraphs that follow, the `dod_gate` node, and the filing-time reference advisory MUST take the governing-heading verdict for each assertion from this component and MUST name the heading it returns as the remedy for a reference that does not govern the assertion; coherence, proof-mode feasibility, rider coherence and every existing refusal remedy remain graded exactly as before, because this component answers only the two questions above. A verdict MUST be reused while the item's effective criteria and referenced headings are byte-unchanged. Scenario 206 in `scenarios.md` exercises this paragraph together with the autonomy-tier bullet below.

In SPECIFICATION/contracts.md, section "Grooming and slice-size calibration" → "The four maintainer touchpoints", touchpoint 1, replace the bullet that begins "**An autonomy tier is assigned**" with:

> - **An autonomy tier is assigned** — the spec-change tier is DECIDED by the spec-stated judgement of §"Effective acceptance criteria", never declared by the filer and never read off `spec_commitment_hint` (which marks an implementation follow-up to an already ratified change). At filing, at groom and again on every dispatch path, every implement-kind item MUST be classified; an item classified `feature` whose asked-for behaviour the judgement reports `partial` or `unstated` is spec-change tier. A spec-change-tier item MUST carry a linked proposed-change topic, filed beside it through `/livespec:propose-change` as the parallel deposit, and the judgement MUST name an existing heading to generalize in preference to a new clause whenever one exists. The item MUST be held out of `ready` until BOTH hold: the linked topic's revision record under `<spec-root>/history/vNNN/proposed_changes/` carries decision `accept` or `modify`, and the judgement, re-run against the ratified specification, returns `stated` for the item's asked-for behaviour. That hold is a read of the spec history and needs no model, so it MUST fail closed; the pre-dispatch wall MUST refuse a held item with exit code `5` naming the unratified topic, and once both conditions hold the next intake or drain pass MUST route the item onward with no human valve. An item classified `bug`, `chore` or `non_functional` is never spec-change tier and routes as every other factory-dispatchable item. When the classification cannot run (no eligible model, a timeout, or an unparseable verdict), intake MUST record that on the item and route it as it would without the classification; the `dod_gate` node, which runs the same judgement in-run, remains the backstop that refuses an unstated feature before any implementation spend. Plan-child disposition refuses a held spec-change-tier child and admits an implementation follow-up.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification

```gherkin
Feature: New behaviour gets new spec before it is built
  As the maintainer keeping the implementation and the specification in lockstep
  I want every feature whose behaviour the spec does not state to wait for its proposal to ratify
  So that implementation never runs ahead of the specification while bugs and chores keep their leeway

  Scenario: An unstated feature is held and the wall refuses it
    Given an implement-kind item typed feature whose asked-for behaviour the spec-stated judgement reports unstated
    When the item is filed
    Then the verdict, the generalization target and the proposed-change topic it must link are recorded on the item
    And the item is spec-change tier and is not routed to ready
    And a dispatch of the item is refused with exit code 5 naming the unratified topic

  Scenario: A bug is routed as today
    Given an implement-kind item the judgement classifies bug
    When the item is filed
    Then it is routed through intake exactly as an item not subject to the tier

  Scenario: Ratification releases the hold without a human valve
    Given a held spec-change-tier item whose linked topic now has a revision record with decision accept
    And the judgement re-run against the ratified spec returns stated for its asked-for behaviour
    When the next intake or drain pass reaches the item
    Then the item is routed to ready with no human valve

  Scenario: A rejected or narrowed proposal does not release the hold
    Given a held spec-change-tier item whose linked topic has a revision record with decision reject
    When the next drain pass reaches the item
    Then the item stays held and the refusal names the topic

  Scenario: A follow-up to a ratified change is not held
    Given an implement-kind item carrying a spec_commitment_hint from a ratified proposal
    When the item is filed
    Then it is not spec-change tier

  Scenario: A classification that cannot run records itself and leaves the backstop
    Given the classification cannot run for a filed feature
    When intake routes the item
    Then the item is routed as it would be without the classification and the did-not-run cause is recorded on it
    And the dod_gate node refuses the item before implement when the judgement in-run reports the behaviour unstated

  Scenario: A citation that does not govern is remedied with the judgement's heading
    Given a ready item whose References line names a heading that does not govern its assertions
    When the pre-admission judgement runs
    Then the item is held with the governing heading the spec-stated judgement returned as the remedy
```
