---
topic: the-tdd-order-guard-classifies
author: claude-opus-5-5
created_at: 2026-11-14T19:12:00Z
---

## Proposal: The TDD-order guard classifies the run's head by the nearest authored commit beneath any engine checkpoint commits

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State how the TDD-order guard classifies the run's head when it decides whether a `fix` or `review_fix` turn may edit an existing product implementation path. The guard reads the nearest commit at or below HEAD that is not an engine checkpoint commit. An open Red there allows the write. A commit there carrying both trailer sets refuses it as `closed-head`, and one carrying no TDD trailers refuses it as `trailer-free-head`. An unreadable head refuses it.

### Motivation

The ratified paragraph "A fix turn grades each tree once, through its commit hook" re-enters a stage on an open Red and directs the turn to complete that commit's Green amend. It does not say how the guard that admits the amend's implementation edit reads the head. Engine checkpoint commits, which carry the `fabro(<run>): <stage>` subjects Scenario 368 recognises, are written above the open Red before the re-entered turn starts.

The guard today classifies HEAD's own message only. A checkpoint commit carries no TDD trailers, so the guard refuses the Green amend's implementation edit as `trailer-free-head`, and the re-entry brief forbids the reset that would put the Red back at HEAD. Every open-Red re-entry over checkpoint commits therefore fails deterministically.

Measured 2026-11-14 on bd-ib-st4obs, run 01M7DE3JH6D2. It FAILED rc=4 at 18:59:31Z after REVIEW_FIX_OPEN_RED_REENTRY re-entered review_fix@2 with two engine checkpoint commits above open Red 99368c555. bd-ib-v7ukma (v0.319.0) fixed the brief half: the commit runner folds the checkpoints onto the open Red. The guard half is carried by bd-ib-yj5dia, whose dispatch-time tier judgement holds it because the ratified text does not state these four behaviours.

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph "**A fix turn grades each tree once, through its commit hook.**", after the sentence "When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at `needs_human` with a cause naming the open Red commit." insert:

"While a `fix` or `review_fix` turn runs, the TDD-order guard that admits or refuses its Edit or Write to an existing product implementation path MUST classify the run's head by the nearest commit at or below HEAD that is not an engine checkpoint commit. An engine checkpoint commit is a single-parent commit whose subject begins `fabro(`, the form Scenario 368 recognises. When that commit is an open Red, the guard MUST allow the Edit or Write. When it carries both trailer sets, the guard MUST refuse the Edit or Write as `closed-head`. When it carries no TDD trailers, the guard MUST refuse the Edit or Write as `trailer-free-head`. When the guard cannot read the run's HEAD, it MUST refuse the Edit or Write. This sentence governs only how the guard classifies the head; its admission of a write that resolves an unmerged path, and of a new module created as a stub beside a pending test change, is unchanged."

2. In SPECIFICATION/scenarios.md, under "## Scenario 199 — A fix turn grades each tree once, through its commit hook", inside the existing gherkin block, after the scenario "An open Red at the stage's visit limit ends at needs_human naming it", add:

```gherkin
  Scenario: An open Red beneath engine checkpoint commits admits the turn's implementation edit
    Given a review_fix turn re-entered to complete an open Red's Green amend
    And two engine checkpoint commits with `fabro(<run>): <stage>` subjects sit above that open Red
    When the turn edits an existing product implementation path
    Then the TDD-order guard allows the edit

  Scenario: A closed or untrailered commit beneath engine checkpoint commits refuses an implementation edit
    Given engine checkpoint commits sit above a commit carrying both TDD trailer sets
    When a fix turn edits an existing product implementation path
    Then the TDD-order guard refuses the edit as closed-head
    And when the commit beneath the checkpoint commits carries no TDD trailers, the guard refuses the edit as trailer-free-head

  Scenario: An unreadable head refuses an implementation edit
    Given the TDD-order guard cannot read the run's HEAD
    When a fix turn edits an existing product implementation path
    Then the guard refuses the edit
```

No H2 heading is added, so tests/heading-coverage.json is unchanged.
