---
topic: an-implement-turn-runs-a
author: claude-opus-5-5
created_at: 2026-11-04T15:47:07Z
---

## Proposal: The gate preview reports every failure even when a check-skip variable is already set

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State that the gate preview neutralizes, for its own run, any variable that skips or relaxes a check (such as LIVESPEC_CHECK_SKIP) that it inherits from the turn's environment. It then runs every check the commit node's hooks would run and reports every failure. Add a Scenario 285 case that exercises this.

### Motivation

The paragraph 'An implement turn sees its commit gate's verdict before it ends.' under ## Self-contained plugin dispatch forbids the preview from SETTING a skip or relax variable. It says nothing about one the preview INHERITS. A turn whose environment already carries LIVESPEC_CHECK_SKIP would get a preview that silently skips the named checks and passes. The commit node's hook then refuses those same checks, which recreates the late, budget-spending refusal the preview exists to prevent. The spec-change-tier judgement on work item bd-ib-cwnt3b (dispatch stage, spec v290, 2026-11-03T23:30:51Z) named exactly this gap and held the item for topic an-implement-turn-runs-a. Measured cost of late refusals: 6 of the last 48 finished factory dispatches (2026-11-04) ended with the implement re-entry budget spent after commit-hook refusals.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph '**An implement turn sees its commit gate's verdict before it ends.**' under ## Self-contained plugin dispatch, replace the sentence

> It MUST NOT pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any check.

with

> It MUST NOT pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any check. When the environment it inherits already carries a variable that skips or relaxes a check, such as `LIVESPEC_CHECK_SKIP`, the preview MUST unset that variable for its own run, MUST run every check the commit node's hooks would run as if the variable were absent, and MUST name each variable it unset in its report beside the exit status and the failed target names.

In SPECIFICATION/scenarios.md, under '## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node', insert after the scenario 'A green turn repairs what its gate preview refuses before it ends':

```gherkin
  Scenario: A gate preview inherits a check-skip variable and still reports the skipped check's failure
    Given a green turn whose environment carries LIVESPEC_CHECK_SKIP naming check-keyword-only-args
    And a change that fails the repository's check-keyword-only-args target
    When the turn runs the gate preview before ending
    Then the preview runs check-keyword-only-args and names it as failed
    And the preview's report names LIVESPEC_CHECK_SKIP as a variable it unset for its run
    And the turn's environment still carries LIVESPEC_CHECK_SKIP after the preview ends
    And no commit was created and no re-entry budget was spent
```

No `## ` heading is added, changed or removed, so tests/heading-coverage.json needs no edit.
