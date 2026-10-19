---
topic: implement-incomplete-fails
author: claude-opus-5-5
created_at: 2026-10-19T02:03:44Z
---

## Proposal: An implement turn that reports its work incomplete fails the implement stage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Decide the implement stage's outcome from a structured completion field in the turn's final output: incomplete, or absent, fails the stage with a partial-progress cause on the existing implement failure edge; complete keeps the succeeded outcome. Add Scenario 202.

### Motivation

Work item bd-ib-ahxcjx (driver gitops-fleet-capacity-monitoring). bd-ib-davaxq run 01M58QNY3ZNM2YCVVB9G2383M0: the implement stage ended with the response 'Partial progress only', having committed only a configuration declaration and one test, and was recorded as succeeded. The run went through janitor, publish_draft and proof_capture before proof_capture found the feature absent and routed to fix, which then timed out building the whole feature in one turn. No ratified clause states when an implement turn succeeds.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Self-contained plugin dispatch", immediately before the paragraph that begins "**Scripted publication and proof-head integrity.**", insert this paragraph:

**An implement turn that ends incomplete does not succeed.** The `implement` stage's outcome MUST be decided from a structured completion field in the turn's final output, not from the turn merely ending. The `implement` prompt MUST direct the turn to end its final reply with that field, stating whether the work item's Definition of Done is complete on the committed branch. When the field reports the work incomplete, the stage MUST end with a failed outcome whose cause names partial progress, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry that cause. A turn whose final output carries no completion field MUST be treated as incomplete. A turn whose field reports the work complete keeps the succeeded outcome and its existing routing. Scenario 202 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append after the last scenario:

## Scenario 202 — An implement turn that reports its work incomplete fails the implement stage

```gherkin
Feature: An incomplete implement turn is not recorded as a success
  As the maintainer of a repository dispatched to the factory
  I want an implement turn that stops partway to end the implement stage as failed
  So that the run does not publish and prove an incomplete change as if it were finished

  Scenario: A turn that reports partial progress fails the stage
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause

  Scenario: A turn with no completion field is treated as incomplete
    Given an implement turn whose final output carries no completion field
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress

  Scenario: A turn that reports its work complete keeps its routing
    Given an implement turn whose final output's completion field reports the Definition of Done complete
    When the implement stage ends
    Then the stage outcome is succeeded and the run proceeds to implementation_diff as before
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the Scenario 202 heading in the same change, with test "TODO" and a reason stating that an integration-tier test is owed and that work-item bd-ib-ahxcjx implements it and owns that binding, plus the matching tests/heading-coverage-debt.json row.
