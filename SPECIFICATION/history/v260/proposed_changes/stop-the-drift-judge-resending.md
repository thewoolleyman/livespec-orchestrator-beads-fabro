---
topic: stop-the-drift-judge-resending
author: claude-opus-5-5:split-drift-check-from-cleanup-timer
created_at: 2026-10-31T18:31:53Z
---

## Proposal: A drift-job run sends the ratified spec tree once per run, not once per merge

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State in the "The drift run." bullet of contracts.md "## The skill surface" that a drift-job run renders the ratified spec tree into one judge prompt for all the merges it judges rather than one prompt per merge, splitting the merges across the fewest prompts that fit only when the content exceeds the judgement's input limit, and reporting the prompt count; findings are still filed one per behaviour per merge with unchanged finding identity. Scenario 207 gains the matching scenario.

### Motivation

Measured in plan split-drift-check-from-cleanup-timer's spend incident: the drift lane resent the whole ratified spec tree once per merge, so a run over N merges paid for N copies of the same spec. The maintainer's 2026-10-25 ruling requires the drift job to stop wasting tokens before it is enabled. Work-item bd-ib-wqciv7 implements the batching; the ratified text states nothing about how merges are packed into judge prompts, so the spec-change tier hold would refuse its dispatch.

### Proposed Changes

In SPECIFICATION/contracts.md, "## The skill surface", append to the "**The drift run.**" bullet, after the sentence ending "judged again against an unchanged ratified spec revision.":

A drift-job run MUST render the ratified spec tree into one judge prompt for all the merges it judges, and MUST NOT send it once per merge; only when that content exceeds the judgement's input limit MUST it split the merges across the fewest prompts that fit, and its `--json` outcome MUST report the count of prompts it sent. Batching MUST NOT change what is filed: the run MUST still file one proposed change per `partial` or `unstated` behaviour per merge, under the same finding identity.

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts", append:

  Scenario: Several merges share one rendering of the spec tree
    Given three merges after the frontier whose combined content fits the judgement's input limit
    When the drift job runs
    Then the ratified spec tree is rendered into one judge prompt for all three merges
    And one proposed change is filed per unstated behaviour per merge under its usual finding identity
    And the outcome reports one prompt sent
