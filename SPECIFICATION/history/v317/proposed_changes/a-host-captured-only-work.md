---
topic: a-host-captured-only-work
author: claude-opus-5-5
created_at: 2026-11-07T20:38:25Z
---

## Proposal: An implement item with no factory-captured assertion is withheld from ready and refused before any factory run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Carries the behaviour of work item bd-ib-3asaxk. An implement-kind item with no factory_captured assertion and a null factory_safety yields a mechanical Definition-of-Done finding at filing, naming the dead-implementer gate and the host route, and rests at pending-approval. A dispatch of such an item is refused before any Fabro run is created, naming the same finding, keeping no claim. An item with at least one factory_captured assertion files and dispatches with no new finding. This generalizes `## Scenario 140 — Filing displays Definition-of-Done findings and withholds ready only on a mechanical one`.

### Motivation

Measured instance, as recorded on bd-ib-3asaxk: tdd-proof-lv352h, run 01M5FF8M02TNVWWN6AEXJ1V7JM on 2026-10-21. Its only assertion sat under `### Host-captured` and its description said no code change was expected. LIVESPEC_PROOF_GRADE_ASSERTIONS decoded to an empty list, the implementer correctly committed nothing, `implementation_diff` failed with LIVESPEC_DEAD_IMPLEMENTER, `dead_implementer` failed, the drive exited 1 with no pull request, and the stranded claim was released by hand.

What is already covered: `## Scenario 266 — A complete implement turn with no diff ends as already satisfied, not as a dead implementer` and its clause in contracts.md ("An implement turn that reports completion with no diff ends as already satisfied", ratified v254, 2026-10-30) end a `red` turn that declares already-satisfied on an unchanged tree without the dead-implementer truncation, release the claim and rest the item in `acceptance`. That covers the ending and the stranded claim of a correct no-op turn that makes the declaration. It does not cover a turn that makes no declaration, which still ends at `dead_implementer`, and it does not stop the dispatch. Scenario 266's Given names factory_captured assertions, so its text says nothing specific about an item that has none.

What remains, as the item states it: a host-captured-only item still takes a factory slot for a run that cannot prove anything, because `proof_capture` has no `factory_captured` assertion to capture; and, on the item's reading, one that owes a code change has its fix in the wrong route.

Design caveat from the item: an all-host-captured item can still owe a code change (precedent livespec-dev-tooling-vxkmab, landed by the host route, whose Reason line reads needs host secrets). So the finding directs to the host route or asks for a factory_captured assertion, and must not imply the work is unneeded.

Alignment: bd-ib-bomy33 will make the approve valve refuse a held item and move a held `ready` item to `backlog`. It concerns the spec-change hold, not this finding, and this rule does not change it. An item withheld here rests at `pending-approval` under the existing mechanical-finding path; `pending-approval` is not a move target, and no move is introduced.

### Proposed Changes

In `SPECIFICATION/contracts.md`, immediately after the paragraph "**The deliverable policy.**" and before "**Derived routing, never stored.**", the spec MUST gain this paragraph:

**An implement item with no factory-captured assertion is routed at filing.** When an implement-kind item's Definition of Done carries at least one gradeable assertion, no assertion is `factory_captured`, and `factory_safety` is null, the host-side wall MUST report a mechanical Definition-of-Done finding that names the dead-implementer gate and the host route. The finding MUST name both remedies: the host route (`set-factory-safety:<id>:<reason>` then `driver-dispatch:<id>`), and adding a `factory_captured` assertion that a sandbox capability can prove. The finding MUST NOT state or imply that the work is unneeded, because an item whose every assertion is host-captured can still owe a code change. Being mechanical, the finding withholds `ready` under the existing wall, so the item rests at `pending-approval`. Every dispatch entry path MUST refuse such an item before any Fabro run is created, with a refusal naming the same finding, and the item MUST keep no claim. An item with at least one `factory_captured` assertion MUST file and dispatch with no finding from this rule, and an item whose `factory_safety` is non-null is not subject to it. The rule keys on the absence of a `factory_captured` assertion alone and reads no declared no-code scope, because no field or section declares one. Scenario 325 in `scenarios.md` exercises this paragraph.

In `SPECIFICATION/scenarios.md`, append after the last scenario:

## Scenario 325 — An implement item with no factory-captured assertion is withheld from ready and refused before any factory run

```gherkin
Feature: An implement item no factory run can prove is routed at filing, not discovered at dead_implementer
  Scenario: Filing reports the finding and the item rests at pending-approval
    Given a filer captures an implement-kind item whose every gradeable assertion sits under a Host-captured sub-heading
    And its factory_safety is null
    When the capture front-end displays the filing and intake routes the filed item
    Then the display shows a mechanical Definition-of-Done finding naming the dead-implementer gate and the host route
    And the finding names adding a factory_captured assertion as the other remedy
    And the finding does not say the work is unneeded
    And the item rests at pending-approval and is not routed to ready
  Scenario: A dispatch of such an item is refused before any run exists
    Given an item carrying that finding reaches a dispatch entry path
    When the dispatch is attempted
    Then the dispatch is refused naming the same finding
    And no Fabro run is created and the item keeps no claim
  Scenario: One factory-captured assertion clears the rule
    Given an implement-kind item with at least one factory_captured assertion and factory_safety null
    When it is filed and dispatched
    Then this rule reports no finding and refuses nothing
  Scenario: A host-routed item is unaffected
    Given an implement-kind item with no factory_captured assertion whose factory_safety is non-null
    When it is filed
    Then this rule reports no finding
```

`tests/heading-coverage.json` MUST gain an entry for the new `## Scenario 325` heading in the same change, per the repository's revise co-edit discipline.
