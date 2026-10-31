---
topic: judge-each-default-branch-merge
author: claude-opus-5-5:split-drift-check-from-cleanup-timer
created_at: 2026-10-31T18:31:51Z
---

## Proposal: A drift-job run judges each merge at most once per ratified spec revision

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State in the "The drift run." bullet of contracts.md "## The skill surface" that a drift-job run reuses the recorded verdict for a merge it already judged against the same ratified spec revision, invokes no model judgement for it, and judges it again only once a newer ratified revision exists; a held finding stopping the frontier does not re-judge the merges behind it. Scenario 207 gains the matching scenario.

### Motivation

The maintainer's 2026-10-25 ruling for plan split-drift-check-from-cleanup-timer requires the split-out drift job to stop wasting tokens before it is enabled. Today a frontier stopped by a failed or held merge leaves every later merge after the frontier, so each run re-judges them all against an unchanged spec, spending a model call per merge per run for verdicts it already has. Work-item bd-ib-qupk5g implements the reuse; the ratified text states nothing about re-judging, so the spec-change tier hold would refuse its dispatch.

### Proposed Changes

In SPECIFICATION/contracts.md, "## The skill surface", append to the "**The drift run.**" bullet, after "enable a schedule that invokes `drift-run`.":

A drift-job run MUST NOT invoke a model judgement for a merge it has already judged against the same ratified spec revision: it MUST reuse that merge's recorded verdict, and it MUST judge the merge again only once a newer ratified spec revision exists. A held or failed finding that stops the frontier MUST NOT cause any merge behind it to be judged again against an unchanged ratified spec revision.

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts", append:

  Scenario: A merge already judged against the same spec revision is not judged again
    Given a merge after the frontier that a drift-job run judged against ratified spec revision vN
    And the frontier is stopped behind an earlier merge
    When the drift job runs again while vN is still the newest ratified revision
    Then that merge's recorded verdict is reused and no model judgement is invoked for it
    When a newer ratified revision exists and the drift job runs
    Then that merge is judged again against the newer revision
