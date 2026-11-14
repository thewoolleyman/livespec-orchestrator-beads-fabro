---
topic: a-fix-turn-s-commits
author: claude-opus-5-5
created_at: 2026-11-14T09:17:13Z
---

## Proposal: The affected-tests gate measures a changed module's coverage over every test module that imports it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State how the affected-tests gate selects the tests for a changed product module and over which tests that module's coverage is measured. The selection is its mirror-paired test module plus every test module that imports it, directly or through another imported module, and coverage is measured over that whole set. When the gate cannot resolve which test modules import a changed product module, the commit hook runs the full check aggregate instead of refusing the commit.

### Motivation

The ratified paragraph 'An implement, fix or review_fix turn's commits run the affected-tests gate.' says the gate runs 'any tests its .py changes select' and that 'the scoped tests and their coverage MUST pass', but it does not say which tests a changed product module selects, nor over which tests its coverage is measured.

The first implementation (livespec-orchestrator-beads-fabro#5085, bd-ib-fde4ie, released in v0.325.0) chose the narrowest reading: each changed module's coverage was measured from its mirror-paired test module alone, at fail-under=100. A module whose lines are executed by other test modules then read as uncovered, so every in-turn commit on such a module was refused. That stopped the fleet factory (hold-gmktec, 2026-11-13 06:09:34Z, STOP-AT-SECOND), and #5085 was reverted by #5142 (1c2a3794e, 2026-11-13T08:16Z).

The re-land of bd-ib-fde4ie widens the selection, and the dispatch-time spec-change-tier judgement of 2026-11-14T09:10:52Z holds it, because that selection rule and its unresolvable-import fallback are not stated in ratified text. Stating them makes the gate never stricter than the full aggregate for coverage reached through imports, keeps Scenario 255's refusal naming each missing line, and keeps the existing 'cannot determine' fallback as the route for a scan that cannot resolve importers.

Measured cost the gate removes: an implement-turn Green amend paid the full 98-target aggregate in its hook in 1,259.53 s (bd-ib-hzul2n run 01M7BMBCD352, 2026-11-14), against 18.52 s for a scoped commit on the reverted gate (bd-ib-3h7dsf run 01M79K37K1D0).

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph '**An implement, fix or review_fix turn's commits run the affected-tests gate.**', insert after the sentence ending 'When the gate cannot determine which test modules read the graph, the commit hook MUST run the full check aggregate instead.' the following sentences:

'The affected tests of a changed product module are its mirror-paired test module together with every test module that imports it, directly or through another module it imports; selecting more test modules than strictly needed is permitted, because over-selection only runs more tests. The gate MUST measure that module's per-file coverage over every test module so selected, never over its mirror-paired test module alone. When the gate cannot determine which test modules import a changed product module, for example because a module is loaded by a dynamic import or a module path cannot be resolved, the commit hook MUST run the full check aggregate instead of refusing the commit. Measured 2026-11-13: a gate that measured coverage from the mirror-paired test module alone, at fail-under=100, refused every in-turn commit on modules covered through other test modules and stopped every factory run (livespec-orchestrator-beads-fabro#5085, reverted by #5142).'

2. In SPECIFICATION/scenarios.md, under '## Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once', add inside the existing gherkin block, after the scenario 'A fix turn's commit that leaves a changed module's lines uncovered is refused with those lines':

```gherkin
  Scenario: A changed module covered only through other test modules passes the affected-tests gate
    Given a fix turn committing a change to a product module whose lines are all executed by test modules that import it, and none by its mirror-paired test module
    When its commit hook runs
    Then the affected-tests gate measures that module's coverage over every test module that imports it
    And the commit is not refused for coverage
    And the full check aggregate is not run

  Scenario: A changed module whose importers cannot be resolved falls back to the full aggregate
    Given a fix turn committing a change to a product module that a test module loads by a dynamic import the gate cannot resolve
    When its commit hook runs
    Then it runs the full check aggregate instead of refusing the commit
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json is unchanged.
