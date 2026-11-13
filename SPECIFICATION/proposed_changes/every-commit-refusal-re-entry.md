---
topic: every-commit-refusal-re-entry
author: claude-opus-5-5
created_at: 2026-11-13T16:31:07Z
---

## Proposal: Every commit-refusal re-entry brief names the failing files from the full recorded output

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every re-entry brief that tells a re-entered implement, fix or review_fix turn why its commit was refused or failed MUST take its failed targets and hook error lines from the commit run's full recorded output, MUST name up to the first 40 failing files with their uncovered lines or measured size plus a count of those omitted, and MUST render that section identically on every route for the same output.

### Motivation

Work item bd-ib-b3qjzq ("Every commit-refusal re-entry brief takes its failing targets and file:line rows from the commit run's full output through one shared, 40-file-capped builder") was refused at dispatch as spec-change tier (generalization target ## ACP node timeouts, linked topic every-commit-refusal-re-entry, spec v365). The recorded rationale: the settled-failed-commit paragraph requires the open-Red re-entry brief to carry failed target names and only the FINAL lines of the run's output; the 40-file cap with uncovered lines and an omitted count is stated only for the implement stage's mechanical re-entry (Scenario 285); and taking file:line rows from the full output for the fix, review_fix and open-Red briefs, and building every route's brief alike, is not stated. Measured 2026-11-11: in bd-ib-e3vbbo run 01M75FQDD4SG and livespec-dev-tooling-b7l6it run 01M75R19RPBJ each refresh-repair resolution commit failed check-per-file-coverage three times; the fix brief named the target, but its error lines were the hook's per-target timing table, so the re-entered turn never saw the uncovered file and lines, and both runs ended failed at fix_commit_settle@3. The aggregate-check blocked class (18 implement endings in 7 days, about $480) gets the same tail-only brief from implement_hook_route. The fleet coordinator ruled ONE fix for all routes: this child lands after bd-ib-wotls4 and before bd-ib-vamn3n, which reuses the same failing-file section rather than adding a second parser.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`.** Insert this paragraph immediately AFTER the paragraph that begins **A settled failed commit run is recorded with its cause.** and BEFORE the paragraph that begins **A commit run outlives a node-timeout cut.**:

> **Every commit-refusal re-entry brief names the failing files from the full recorded output.** This paragraph governs every re-entry brief that tells a re-entered ACP turn of the implement-work-item workflow why its commit was refused or failed: the brief `implement_hook_route` writes when it re-enters the implement stage after a refused commit, whether that re-entry is ordinary or mechanical; the brief a re-entered `fix` or `review_fix` turn receives after `fix_commit_settle` or `review_fix_commit_settle` settled a commit run as `failed`; and the open-Red brief of `fix_open_red_route` and `review_fix_open_red_route` after such a settle. Each such brief MUST take its failed target names and hook error lines from the commit run's full recorded output, never only from its final lines, so that output ending in the hook's per-target timing table still yields the files that failed. Each such brief MUST carry a failing-file section that names each failing file the failed targets' recorded output reports, with the uncovered lines or measured size that output gives for it, for at most the first 40 such files in that output's order, and when the output reports more it MUST state how many further files it omitted. Given the same recorded output, every one of those routes MUST produce an identical failed-target and failing-file section, so that a change to how that output is read, or to the 40-file cap, changes every route's brief alike. This paragraph adds content to those briefs only: it changes no route a refusal takes, no re-entry budget, and none of what "A settled failed commit run is recorded with its cause" requires the settle node's own output to state. The failing-file requirement of "A purely mechanical commit refusal has its own re-entry budget" is the mechanical-re-entry case of this paragraph. Scenario 179 in `scenarios.md` exercises this paragraph.

**Edit 2 — `SPECIFICATION/scenarios.md`, §"Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "A re-entered review_fix turn is told why its Green amend failed". The scenario's heading is unchanged.

```gherkin
  Scenario: A re-entered fix turn's brief names the uncovered files from the full recorded output
    Given a fix_commit_settle node that settled a fix commit run as failed on check-per-file-coverage
    And that commit run's recorded output names src/a.py with uncovered lines 10-12 before the per-target timing table that ends the output
    When the run re-enters fix
    Then the re-entry brief names the failed target check-per-file-coverage
    And it names src/a.py with uncovered lines 10-12

  Scenario: An ordinary implement re-entry after a refused commit names the failing files
    Given an implement turn whose commit was refused by a hook whose recorded output names check-lint and check-per-file-coverage
    And that output names src/b.py with uncovered lines 4-9 before the per-target timing table that ends the output
    When implement_hook_route re-enters implement spending its ordinary re-entry
    Then the re-entry brief names check-lint and check-per-file-coverage
    And it names src/b.py with uncovered lines 4-9

  Scenario: The open-Red brief names the failing files from the full recorded output
    Given a review_fix_commit_settle node that settled a Green amend as failed on check-per-file-coverage
    And that commit run's recorded output names src/c.py with uncovered lines 20-21 before the per-target timing table that ends the output
    And the last authored commit is still an open Red
    When review_fix_open_red_route re-enters review_fix
    Then the open-Red brief names src/c.py with uncovered lines 20-21

  Scenario: Every route's failing-file section is capped at forty and identical for the same output
    Given a commit run whose recorded output names only check-per-file-coverage and reports 55 files below the coverage threshold
    When implement_hook_route, a fix re-entry after fix_commit_settle and review_fix_open_red_route each build a re-entry brief from that output
    Then each brief names the first 40 of those files in the output's order, each with its uncovered lines
    And each brief states that 15 further files were omitted
    And the three briefs' failed-target and failing-file sections are identical
```
