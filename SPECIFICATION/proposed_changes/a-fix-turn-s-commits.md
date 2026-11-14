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

State how the affected-tests gate selects tests for a changed product module, and which lines it may refuse a commit for. Selection is every test module that imports the module directly, or imports a module that (transitively) imports it. Before refusing, the selection is widened by a bounded, statically detectable set: test modules whose text names the changed module, and test modules containing a dynamic-import call whose module argument is not a string literal.

The gate refuses only for CHANGED lines that the widened selection leaves unexecuted. Changed lines are the lines the run's branch added or modified against its base. Unchanged lines are never refused at commit time. They were judged by the default branch's full aggregate, and if the branch makes an unchanged line unexecuted (by deleting a test or changing a caller), the janitor's single full check aggregate still catches it.

The proposal states the residual honestly. A changed line executed only through a path the widening cannot see (a dynamic import made inside a product module, a conftest fixture, a subprocess) can still be refused in-turn, and the janitor's aggregate stays the authority. Every in-turn coverage refusal is made countable: one machine-readable line naming the module and the lines, which the run's exported record carries.

### Motivation

The ratified paragraph 'An implement, fix or review_fix turn's commits run the affected-tests gate.' says the gate runs 'any tests its .py changes select' and that 'the scoped tests and their coverage MUST pass', but it does not say which tests a changed product module selects, nor over which tests its coverage is measured.

The first implementation (livespec-orchestrator-beads-fabro#5085, bd-ib-fde4ie, released in v0.325.0) chose the narrowest reading: each changed module's coverage was measured from its mirror-paired test module alone, at fail-under=100. A module whose lines are executed by other test modules then read as uncovered, so every in-turn commit on such a module was refused. That stopped the fleet factory (hold-gmktec, 2026-11-13 06:09:34Z, STOP-AT-SECOND), and #5085 was reverted by #5142 (1c2a3794e, 2026-11-13T08:16Z).

The re-land of bd-ib-fde4ie widens the selection, and the dispatch-time spec-change-tier judgement of 2026-11-14T09:10:52Z holds it, because that selection rule is not stated in ratified text.

Two constraints shape the rule. First, a static import scan cannot see an importer it cannot resolve: a dynamic import, or a module path built at runtime. A fallback conditioned on 'the gate cannot determine its importers' is therefore not detectable, and an unseen importer would under-read coverage and refuse the commit, which is the #5085 failure. Second, the commit-time gate must not pay a whole-test-suite coverage run. The check-per-file-coverage leg, which runs the whole suite with coverage, measured 3654.8 s and 3765 s in a fix turn's hook, longer than the 3600 s fix node limit (the ratified 'A fix turn grades each tree once, through its commit hook.').

A scoped gate cannot be proven never stricter than the whole suite, because a test can reach a module through a route that no cheap scan sees. Examples are a product module that loads another by a dynamic import (`_dispatcher_helper_materialize.py` loads its registry module through `importlib.import_module` on a constant), a conftest fixture, `runpy`, or a subprocess. The rule therefore limits the false-refusal surface rather than claiming it is zero. Limiting refusals to changed lines shrinks that surface from the whole module to the edit itself, and loses no guarantee. Unchanged lines were judged by the default branch's full aggregate, and a branch that makes one unexecuted is still caught by the janitor's full aggregate, which judges whole-module coverage once per run. Making each in-turn coverage refusal countable means a rise in refusals shows on the board before it can stop the factory, the way #5085 did. The bounded widening keeps a refusal's cost to a scoped run, not the whole-suite coverage leg.

Measured cost the gate removes: an implement-turn Green amend paid the full 98-target aggregate in its hook in 1,259.53 s (bd-ib-hzul2n run 01M7BMBCD352, 2026-11-14), against 18.52 s for a scoped commit on the reverted gate (bd-ib-3h7dsf run 01M79K37K1D0).

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph '**An implement, fix or review_fix turn's commits run the affected-tests gate.**', insert after the sentence ending 'When the gate cannot determine which test modules read the graph, the commit hook MUST run the full check aggregate instead.' the following sentences:

'The affected tests of a changed product module are every test module that imports it directly, or imports a module that (transitively) imports it. Selecting more test modules than strictly needed is permitted, because over-selection only runs more tests. The gate MUST NOT measure that module's coverage over any narrower set, such as only the test module whose path mirrors the module's. Before the gate refuses a commit for coverage, it MUST widen the selected test modules with every test module whose text names the changed module (by its dotted module name or the final component of that name), and every test module containing a dynamic-import call (such as `importlib.import_module` or `__import__`) whose module argument is not a string literal. It MUST re-measure that module's line execution over the widened set. The gate MUST refuse only for CHANGED lines that the widened set leaves unexecuted. CHANGED lines are the module's executable lines, as the coverage tool measures them and honouring its exclusion pragmas, that the run's working branch adds or modifies relative to the merge-base of that branch with the default branch at the time of the commit. A module the branch adds, renames or moves counts as wholly changed. A deleted line is not a line of the module. The refusal MUST name that module and each of those lines, and MUST report its failed target as `check-check-coverage-incremental`. A line the branch did not change MUST NOT cause an in-turn refusal: whole-module coverage, against the threshold `check-per-file-coverage` applies, is judged by the `janitor` stage's full check aggregate. Neither measurement runs the full check aggregate. A changed line executed only through a route the widening cannot see, such as a dynamic import made inside a product module, a conftest fixture or a subprocess, can still be refused in-turn; the `janitor` stage's full check aggregate remains the authority on coverage. Every in-turn coverage refusal MUST print one line beginning `LIVESPEC_INTURN_COVERAGE_REFUSAL:` that names the module and each refused line, in the commit run's own recorded output, so the run's exported record carries it and in-turn coverage refusals can be counted across runs. Measured 2026-11-13: a gate that measured coverage from the test module whose path mirrors the changed module's alone, at fail-under=100, refused every in-turn commit on modules covered through other test modules and stopped every factory run (livespec-orchestrator-beads-fabro#5085, reverted by #5142).'

2. In SPECIFICATION/scenarios.md, under '## Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once', add inside the existing gherkin block, immediately after the scenario that change 3 below renames to 'A fix turn's commit that leaves a changed line uncovered is refused with those lines' (apply change 3 first):

```gherkin
  Scenario: A changed module covered only through other test modules passes the affected-tests gate
    Given a fix turn committing a change to a product module whose changed lines are all executed by test modules that import it, and none by the test module whose path mirrors the module's
    When its commit hook runs
    Then the affected-tests gate measures that module's coverage over every test module that imports it, not over the mirroring test module alone
    And the commit is not refused for coverage
    And the full check aggregate is not run

  Scenario: A coverage gap the importing tests show is re-measured over the widened set before the commit is refused
    Given a fix turn committing a change to a product module whose changed lines are executed only by a test module that loads it with importlib.import_module and a module name built at runtime
    When its commit hook runs and the test modules that import it leave those lines unexecuted
    Then the gate re-measures that module's line execution over the importing test modules, every test module naming the module, and every test module with a non-literal dynamic-import call
    And the commit is not refused for coverage, because that widened set executes those lines
    And the full check aggregate is not run

  Scenario: An unchanged line the selected tests leave unexecuted does not refuse the commit
    Given a fix turn committing a change to a product module, one of whose lines the run's branch did not change is executed only by a test module the widened set does not include
    When its commit hook runs
    Then the commit is not refused for that unchanged line
    And the janitor stage's full check aggregate still judges that module's whole-module coverage

  Scenario: An in-turn coverage refusal is countable
    Given a fix turn committing a change that leaves a changed line of a product module unexecuted by the widened set
    When its commit hook refuses the commit for coverage
    Then the commit run's recorded output carries one line beginning LIVESPEC_INTURN_COVERAGE_REFUSAL: naming that module and each refused line
```

3. In SPECIFICATION/scenarios.md, in the same Scenario 255 block, replace the existing scenario

```gherkin
  Scenario: A fix turn's commit that leaves a changed module's lines uncovered is refused with those lines
    Given a fix turn committing a change that leaves lines of a product module it changed uncovered
    When its commit hook runs
    Then the commit is refused with a per-file coverage failure naming that module and each missing line
    And the full check aggregate is not run
```

with

```gherkin
  Scenario: A fix turn's commit that leaves a changed line uncovered is refused with those lines
    Given a fix turn committing a change that leaves lines it added or modified in a product module unexecuted by the widened set of test modules
    When its commit hook runs
    Then the commit is refused with a coverage failure naming that module and each changed line left uncovered
    And the full check aggregate is not run
```

4. Align the three ratified sentences that say the scoped tests' coverage must pass, so they mean the changed-line rule of change 1 and do not demand whole-module coverage at commit time:
   - In SPECIFICATION/contracts.md, paragraph '**An implement, fix or review_fix turn's commits run the affected-tests gate.**', replace 'at the Green amend and every later commit, the scoped tests and their coverage MUST pass.' with 'at the Green amend and every later commit, the scoped tests MUST pass and every changed line of each changed product module MUST be executed by the widened set of test modules, as defined above.'
   - In SPECIFICATION/contracts.md, paragraph '**A fix turn grades each tree once, through its commit hook.**', replace 'the affected-tests gate's scoped tests and their coverage, or the full check aggregate when that gate cannot scope the change' with 'the affected-tests gate's scoped tests and its changed-line coverage, or the full check aggregate when that gate cannot scope the change'.
   - In SPECIFICATION/scenarios.md, Scenario 255's scenario 'A Red commit and its Green amend go through the affected-tests gate', replace 'Then the commit hook runs the affected-tests gate and requires the scoped tests and their coverage to pass' with 'Then the commit hook runs the affected-tests gate and requires the scoped tests to pass and every changed line to be executed by the widened set'.

No H2 heading is added, changed or removed, so tests/heading-coverage.json is unchanged.
