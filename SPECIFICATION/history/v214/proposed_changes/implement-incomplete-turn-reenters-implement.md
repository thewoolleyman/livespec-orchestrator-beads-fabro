---
topic: implement-incomplete-turn-reenters-implement
author: claude-opus-5-5
created_at: 2026-10-25T03:28:00Z
---

## Proposal: Every incomplete implement turn re-enters implement while its retry budget remains

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

v208 re-enters `implement` only when an incomplete turn's latest commit attempt was refused by the commit hook. This widens the re-entry to EVERY incomplete turn — a completion field reporting the work incomplete, or no completion field at all — while the `implement` node's retry budget is not exhausted. The re-entered brief carries the previous turn's latest failing gate from the run's recorded tool output: the refused commit's hook verdict when there is one, otherwise the failed targets and error lines of the turn's latest run of the repository's check suite, otherwise a statement that the turn ended incomplete with no recorded failing gate. An exhausted budget fails as before: naming the hook's failed targets after a refused commit, and naming partial progress otherwise.

### Motivation

Stability tier, maintainer-directed through coordinator gitops-fleet-capacity-monitoring on 2026-10-25 ("implement all of your recommendations"), ahead of any Codex re-canary. Two measured endings that v208 does not recover: bd-ib-idpr32 run 01M5QVBJ2573 quit at about 52 minutes of a four-hour allowance with only check-per-file-coverage and check-coverage failing in its own check-suite run and no hook refusal, so the v208 arm did not fire; bd-ib-3kqdln run 01M5QW46JGG0 ended at about 24 minutes with no completion field. Both rested for a human with the turn allowance mostly unspent, and both failures were fixable gates the agent had already observed.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch", paragraph "An implement turn that ends incomplete does not succeed", replace the sentences:

> When the field reports the work incomplete, the stage MUST end with a failed outcome whose cause names partial progress, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry that cause, unless the turn's latest commit attempt was refused as defined below. A turn's latest commit attempt counts as refused when the turn left changes staged and the repository's commit hook, run by the run itself over those staged changes, exits non-zero naming at least one failed target; a turn that left nothing staged, or whose staged changes the hook accepts, did not leave a refused commit attempt. When an incomplete turn's latest commit attempt was refused and the `implement` node's retry budget is not exhausted, the run MUST re-enter the `implement` stage instead of failing it, and the re-entered turn's brief MUST carry the refused commit's failed target names and the hook's own error lines, taken from the hook's recorded output rather than from the previous turn's reply. When that budget is exhausted, the stage MUST end with a failed outcome whose cause names the hook's failed targets, and the dispatch outcome detail MUST carry that cause.

with:

> A turn's latest commit attempt counts as refused when the turn left changes staged and the repository's commit hook, run by the run itself over those staged changes, exits non-zero naming at least one failed target; a turn that left nothing staged, or whose staged changes the hook accepts, did not leave a refused commit attempt. When the field reports the work incomplete and the `implement` node's retry budget is not exhausted, the run MUST re-enter the `implement` stage instead of failing it. The re-entered turn's brief MUST carry the previous turn's latest failing gate, taken from the run's recorded tool output rather than from the previous turn's reply, chosen in this order: when the turn's latest commit attempt was refused, the refused commit's failed target names and the hook's own error lines; otherwise, when the turn's latest run of the repository's check suite exited non-zero naming at least one failed target, those failed target names and that run's error lines; otherwise, a statement that the previous turn ended incomplete with no recorded failing gate. When that budget is exhausted, the stage MUST end with a failed outcome, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry its cause: the hook's failed targets when the turn's latest commit attempt was refused, and partial progress otherwise.

In SPECIFICATION/scenarios.md, "## Scenario 204 — An implement turn that reports its work incomplete fails the implement stage", replace the first two scenario blocks:

```gherkin
  Scenario: A turn that reports partial progress fails the stage
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left nothing staged
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause

  Scenario: An incomplete turn whose staged changes the commit hook accepts fails as partial progress
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left changes staged that the repository's commit hook accepts
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
```

with:

```gherkin
  Scenario: A turn that reports partial progress re-enters implement while its retry budget remains
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left nothing staged and made no failing run of the repository's check suite
    And the implement node's retry budget is not exhausted
    When the implement stage ends
    Then the run re-enters the implement stage instead of failing it
    And the re-entered turn's brief states that the previous turn ended incomplete with no recorded failing gate

  Scenario: An incomplete turn whose own check-suite run failed re-enters with that run's failed targets
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left no refused commit attempt
    And the turn's latest run of the repository's check suite exited non-zero naming failed targets
    And the implement node's retry budget is not exhausted
    When the implement stage ends
    Then the run re-enters the implement stage instead of failing it
    And the re-entered turn's brief carries those failed target names and that run's error lines, taken from the run's recorded tool output

  Scenario: An incomplete turn whose staged changes the commit hook accepts re-enters implement
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left changes staged that the repository's commit hook accepts
    And the implement node's retry budget is not exhausted
    When the implement stage ends
    Then the run re-enters the implement stage instead of failing it

  Scenario: An incomplete turn with no refused commit and its retry budget exhausted fails as partial progress
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left no refused commit attempt
    And the implement node's retry budget is exhausted
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause
```

and replace the block:

```gherkin
  Scenario: A turn with no completion field is treated as incomplete
    Given an implement turn whose final output carries no completion field
    And the turn left nothing staged
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
```

with:

```gherkin
  Scenario: A turn with no completion field is treated as incomplete and re-enters implement
    Given an implement turn whose final output carries no completion field
    And the turn left nothing staged
    And the implement node's retry budget is not exhausted
    When the implement stage ends
    Then the run re-enters the implement stage instead of failing it

  Scenario: A turn with no completion field and its retry budget exhausted fails as partial progress
    Given an implement turn whose final output carries no completion field
    And the turn left nothing staged
    And the implement node's retry budget is exhausted
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
```

The Scenario 204 heading is unchanged, so tests/heading-coverage.json needs no co-edit.
