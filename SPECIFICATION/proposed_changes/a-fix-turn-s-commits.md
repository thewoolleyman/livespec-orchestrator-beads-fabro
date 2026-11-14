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

State how the affected-tests gate selects the tests for a changed product module and over which tests that module's coverage is measured. The selection is every test module that imports it directly, or imports a module that (transitively) imports it, and coverage is judged against the threshold check-per-file-coverage applies. A coverage refusal from that selection is never taken on that selection alone: before refusing, the gate re-measures over a bounded, statically detectable widening of the selection. The widening adds every test module whose text names the changed module, and every test module containing a dynamic-import call whose module argument is not a string literal. The gate refuses only for lines that the widened selection also leaves unexecuted. The gate therefore never refuses for an importer it could have missed, and never runs the whole test suite at commit time.

### Motivation

The ratified paragraph 'An implement, fix or review_fix turn's commits run the affected-tests gate.' says the gate runs 'any tests its .py changes select' and that 'the scoped tests and their coverage MUST pass', but it does not say which tests a changed product module selects, nor over which tests its coverage is measured.

The first implementation (livespec-orchestrator-beads-fabro#5085, bd-ib-fde4ie, released in v0.325.0) chose the narrowest reading: each changed module's coverage was measured from its mirror-paired test module alone, at fail-under=100. A module whose lines are executed by other test modules then read as uncovered, so every in-turn commit on such a module was refused. That stopped the fleet factory (hold-gmktec, 2026-11-13 06:09:34Z, STOP-AT-SECOND), and #5085 was reverted by #5142 (1c2a3794e, 2026-11-13T08:16Z).

The re-land of bd-ib-fde4ie widens the selection, and the dispatch-time spec-change-tier judgement of 2026-11-14T09:10:52Z holds it, because that selection rule is not stated in ratified text.

Two constraints shape the rule. First, a static import scan cannot see an importer it cannot resolve: a dynamic import, or a module path built at runtime. A fallback conditioned on 'the gate cannot determine its importers' is therefore not detectable, and an unseen importer would under-read coverage and refuse the commit, which is the #5085 failure. Second, the commit-time gate must not pay a whole-test-suite coverage run. The check-per-file-coverage leg, which runs the whole suite with coverage, measured 3654.8 s and 3765 s in a fix turn's hook, longer than the 3600 s fix node limit (the ratified 'A fix turn grades each tree once, through its commit hook.').

The widening before refusal meets both constraints. It adds only test modules a scan can find with no knowledge of what it missed: every module whose text names the changed module (its dotted module name, its file name or its module name), and every module containing a dynamic-import call whose module argument is not a string literal. Such a call is the only way a test module can load the changed module without naming it. The widening is bounded to those modules, so a refusal costs a scoped run, not the whole suite. Scenario 255's ratified refusal ('refused with a per-file coverage failure naming that module and each missing line ... the full check aggregate is not run') still holds.

Measured cost the gate removes: an implement-turn Green amend paid the full 98-target aggregate in its hook in 1,259.53 s (bd-ib-hzul2n run 01M7BMBCD352, 2026-11-14), against 18.52 s for a scoped commit on the reverted gate (bd-ib-3h7dsf run 01M79K37K1D0).

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph '**An implement, fix or review_fix turn's commits run the affected-tests gate.**', insert after the sentence ending 'When the gate cannot determine which test modules read the graph, the commit hook MUST run the full check aggregate instead.' the following sentences:

'The affected tests of a changed product module are every test module that imports it directly, or imports a module that (transitively) imports it; selecting more test modules than strictly needed is permitted, because over-selection only runs more tests. The gate MUST judge that module's per-file coverage, against the same threshold `check-per-file-coverage` applies, over every test module so selected, and MUST NOT judge it over any narrower set, such as only the test module whose path mirrors the module's. A per-file coverage gap the selected test modules show MUST NOT be final. Before refusing, the gate MUST re-measure that module's coverage over the selected test modules together with every test module whose text names the changed module (by its dotted module name, its file name or its module name) and every test module containing a dynamic-import call (such as `importlib.import_module` or `__import__`) whose module argument is not a string literal. It MUST refuse only for the lines that this widened set also leaves unexecuted, naming that module and each of those lines. Neither measurement runs the whole test suite or the full check aggregate. Measured 2026-11-13: a gate that measured coverage from the test module whose path mirrors the changed module's alone, at fail-under=100, refused every in-turn commit on modules covered through other test modules and stopped every factory run (livespec-orchestrator-beads-fabro#5085, reverted by #5142).'

2. In SPECIFICATION/scenarios.md, under '## Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once', add inside the existing gherkin block, after the scenario 'A fix turn's commit that leaves a changed module's lines uncovered is refused with those lines':

```gherkin
  Scenario: A changed module covered only through other test modules passes the affected-tests gate
    Given a fix turn committing a change to a product module whose lines are all executed by test modules that import it, and none by the test module whose path mirrors the module's
    When its commit hook runs
    Then the affected-tests gate measures that module's coverage over every test module that imports it, not over the mirroring test module alone
    And the commit is not refused for coverage
    And the full check aggregate is not run

  Scenario: A coverage gap the importing tests show is re-measured over the widened set before the commit is refused
    Given a fix turn committing a change to a product module whose lines are executed only by a test module that loads it with importlib.import_module and a module name built at runtime
    When its commit hook runs and the test modules that import it leave those lines unexecuted
    Then the gate re-measures that module's coverage over the importing test modules, every test module naming the module, and every test module with a non-literal dynamic-import call
    And the commit is not refused for coverage, because that widened set executes those lines
    And neither the whole test suite nor the full check aggregate is run

  Scenario: A coverage gap no widened test executes is refused with those lines
    Given a fix turn committing a change that leaves lines of a product module it changed unexecuted by every test module that imports it, names it, or makes a non-literal dynamic-import call
    When its commit hook runs
    Then the commit is refused with a per-file coverage failure naming that module and each of those lines
    And neither the whole test suite nor the full check aggregate is run
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json is unchanged.
