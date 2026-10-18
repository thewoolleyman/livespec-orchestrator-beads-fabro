---
topic: fix-turn-suite-once
author: claude-opus-5-5
created_at: 2026-10-18T11:27:53Z
---

## Proposal: A fix turn runs the check suite once per tree and counts a commit hook's full green run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

State the fix turn's check-suite obligation: leave the branch at a head whose full suite passed in the turn; a commit whose pre-commit hook ran the full suite green on the exact committed tree satisfies it, so the fix prompt directs no second run on that tree; a partial hook run or a later tree change still requires a full run; refresh-repair rounds follow the same rule. Add Scenario 199.

### Motivation

Work item bd-ib-k6dwyv (finding F-ak, admitted by driver ruling R168 of gitops-fleet-capacity-monitoring). Run 01M56YAEWMS8 of bd-ib-spc6xr on 2026-10-18: the fix turn committed 7b909571 with its hook running the full aggregate green in 1364 s, then launched a second redundant `just check`; the 3600 s turn limit killed it and the run ended at needs_human. The fix prompt's check-suite steps carry no exemption for a hook's full green run, and no ratified text states the fix turn's check-suite obligation at all, so the item's references cannot govern it at dod_gate. The janitor already re-runs the suite after every fix visit.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Self-contained plugin dispatch", immediately after the paragraph that ends "…so only proof for the repaired head can reach publication." (the refresh-repair paragraph), insert this paragraph:

**A fix turn runs the check suite once per tree.** The `fix` turn MUST leave the run's working branch at a head on which the repository's sandbox check suite has passed in full during that turn. That applies both to a fix round and to the integrated tree of a refresh-repair round. A commit whose repository pre-commit hook ran the full check suite to a passing result on the exact tree it committed satisfies this obligation for that tree. The `fix` prompt MUST NOT direct a second run of the suite on that same tree in the same turn, because the `janitor` visit that follows every `fix` visit runs the suite again in any case. A hook run that covered only part of the suite, such as a Red commit on the hook's fast path, does not satisfy the obligation. A change to the tree after the last passing full run means the suite MUST be run in full again before the turn ends. Scenario 199 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, after Scenario 198, append:

## Scenario 199 — A fix turn runs the check suite once per tree and counts a commit hook's full green run

```gherkin
Feature: A fix turn does not spend its time limit on a duplicate check suite
  As the maintainer of a repository dispatched to the factory
  I want a fix turn to count a commit hook's full green suite run as the turn's suite run
  So that two full runs of a long suite do not exhaust the fix node's time limit

  Scenario: A commit whose hook ran the full suite green ends the turn's suite obligation for that tree
    Given a fix turn that commits its change
    And the repository pre-commit hook ran the full check suite to a passing result on the committed tree
    When the fix turn completes its work on that tree
    Then the fix prompt directs no second run of the suite on that tree in the same turn

  Scenario: A partial hook run or a later change still requires a full run
    Given a fix turn whose only commit took the hook's partial fast path, or whose tree changed after its last full passing run
    When the fix turn completes its work
    Then the fix prompt directs a full run of the check suite before the turn ends

  Scenario: A refresh-repair round applies the same rule to the integrated tree
    Given a fix turn entered with a refresh-repair brief
    And its commit on the integrated tree ran the full check suite green through the pre-commit hook
    When the turn completes the repair
    Then the fix prompt directs no second run of the suite on that integrated tree in the same turn
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the Scenario 199 heading in the same change, with test "TODO" and a reason stating that an integration-tier test is owed and that work-item bd-ib-k6dwyv implements it and owns that binding, plus the matching tests/heading-coverage-debt.json row.
