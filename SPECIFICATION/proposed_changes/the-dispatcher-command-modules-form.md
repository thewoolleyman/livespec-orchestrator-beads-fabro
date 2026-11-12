---
topic: the-dispatcher-command-modules-form
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-12T05:49:52Z
---

## Proposal: Every test module collects when selected on its own, and every product module imports first

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

A full-suite run can hide an import cycle among product modules. The suite collects because some earlier module happens to import the cycle's members in a working order, so a test module that imports a cycle member first fails collection only when it is selected on its own. A factory implement turn's targeted Red-Green run selects exactly that way. This proposal adds one forbidden pattern to constraints.md, beside the existing rule against real-time sleeps in tests. Every test module under `tests/` MUST collect when pytest selects it on its own, whatever order the rest of the suite would import modules in. Every product module of the plugin package MUST import successfully as the first plugin module in a fresh interpreter. Two named checks enforce them, and each repository arms them in its `just check` aggregate only after its own tree passes them. One new un-numbered scenario exercises the rule.

### Motivation

Owning work item bd-ib-vc6o5q, "The Dispatcher command modules form an import cycle through _dispatcher_fabro_reattach, so a test that imports the reattach module first fails collection and blocks every targeted Red-Green run on it". At filing and again at 05:47:25Z on spec v358, its classify-tier judgement read partial and held it for this topic: "The ratified text does not state the main requirement, that the reattach coverage module collects and passes when run alone. That is an internal import-structure property, and no visible clause covers it." legacy-coordinator-agent routed this topic, generalized, as a real rule worth having (2026-11-12 about 05:55Z).

Measured on master 97fe667b0: `pytest --collect-only` on tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reattach_watch_coverage.py alone fails with "ImportError: cannot import name 'ReattachRun' from partially initialized module 'livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach' (most likely due to a circular import)". The cycle runs `_dispatcher_fabro_reattach` -> `_dispatcher_run_watch_decision` -> `_dispatcher_stall_cancel` -> `_dispatcher_engine` -> `_dispatcher_post_run_terminal` -> `_dispatcher_fabro_reattach`, and fdcbefbb9 (bd-ib-pxp2ve) introduced it. Master CI stays green because the full suite imports the engine first. The cost landed on bd-ib-ag633q: its FRESH run 01M772057DRH spent two implement turns and rested at needs-human with empty diffs after its targeted run hit the collection failure. Nothing in the aggregate notices this class today.

Measured cost, on this repository's dev host on 2026-11-12 about 05:57Z, under host load (CPU PSI about 60), over a fixed sample of 20 modules each, every invocation including mise and uv startup. There are 1,680 test modules and 1,017 product modules, on 18 cores. Collection alone took 6.6 s per module, so collecting every test module would cost about 185 CPU-minutes, or about 10 minutes of wall time at 18-way parallelism. That is too large a runtime increase to add to the aggregate without the maintainer's word. Importing a product module first took 2.0 s per module, about 34 CPU-minutes for all of them, or about 2 minutes of wall time at 18-way parallelism. So the import-first check covers every product module. The collect-alone check covers only the test modules a change adds or modifies, typically a handful per change, costing seconds. That catches the measured defect class at a small fraction of a full collect-alone pass, and neither check runs any test. All sampled modules passed both checks on master 97fe667b0, so today's measured cycle is caught by importing `_dispatcher_fabro_reattach` first, not by a sampled module.

Placement: this is a contributor-facing rule about this repository's own test suite and product package, enforced by its own `just check` aggregate, exactly as the neighbouring "No real-time sleeps or wall-clock verdicts in tests" bullet is. So it belongs in constraints.md §"Forbidden patterns". Fleet scope: the same order-dependent collection can hide in every fleet repository whose CI collects only the full suite. The two checks are named here so that livespec-dev-tooling can ship them as canonical shared checks for the fleet. That shared realization is a livespec-dev-tooling item filed after this topic is ratified. Its Definition of Done adopts before it arms: each repository's tree passes the checks first, and only then are they armed there. It is not part of this repository's requirement.

In-flight survey: the open spec PRs #5005 (a-needs-human-rest-overwrites) and #4999 (revise plan-record-artifact-paths-include-imported-code) and the pending in-tree proposals touch no part of §"Forbidden patterns". Nothing to align with.

### Proposed Changes

1. constraints.md, §"Forbidden patterns": IMMEDIATELY AFTER the bullet that begins "- No real-time sleeps or wall-clock verdicts in tests." (which ends "for a test whose subject is real time itself."), insert this bullet as the section's next list item:

"- No order-dependent test collection or product-module import. Every test module under `tests/` MUST collect when pytest selects that module on its own in a fresh process, whatever order the rest of the suite would import modules in. Every product module under `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/` MUST import successfully as the first module of that package in a fresh interpreter. An import cycle among product modules that resolves only because some other module was imported first violates both rules. Two checks enforce them, and a repository MUST NOT arm either check in its `just check` aggregate until its own tree passes that check; ratifying this rule arms nothing by itself. For check-test-modules-collect-alone, a tree passes when one run of its full mode passes. `check-test-modules-collect-alone` MUST run collection only (`pytest --collect-only`), in its own fresh process, for each test module under `tests/` that the change under test adds or modifies relative to its merge base with the default branch, or on a push to the default branch, relative to the pushed range's previous head; a renamed module counts as modified and a deleted one is skipped. The check MUST also offer a full mode that collects every test module under tests/. It MUST NOT run the module's tests, and it MUST refuse naming each module that fails collection and its error. An unchanged test module that imports a product module first is largely covered by `check-product-modules-import-first`, because a cycle among product modules makes that product module fail to import first; an order dependence in a helper module under `tests/`, such as a `conftest.py`, is caught only by the full mode. `check-product-modules-import-first` MUST import every product module first, each in its own fresh interpreter, and MUST refuse naming each module that fails to import and its error. check-product-modules-import-first starts exactly one interpreter per product module. check-test-modules-collect-alone starts exactly one collection process per added or modified test module, and none for an unchanged one. Either check MAY run its modules in parallel, and MUST report every failing module rather than stopping at the first."

No other bullet of the section changes.

2. scenarios.md: append one new H2 section at the end of the file, after the last existing section, separated from it by one blank line:

## Scenario: a test module or product module that works only after another import is refused by the aggregate

```gherkin
Feature: a test module or product module that works only after another import is refused by the aggregate

  Scenario: a test module that fails collection on its own is refused
    Given product modules A and B import each other at module level
    And the full test suite collects because an earlier test module imports B before A
    And test module T, which the change under test adds, imports A before any other product module
    When the just check aggregate runs check-test-modules-collect-alone
    Then the check refuses
    And it names T and its collection error

  Scenario: a product module that fails to import first is refused
    Given product modules A and B import each other at module level, so that importing A first fails
    When the just check aggregate runs check-product-modules-import-first
    Then the check refuses
    And it names A and its import error

  Scenario: every failing module is reported
    Given two test modules, both added or modified by the change under test, that each fail collection on their own
    When the just check aggregate runs check-test-modules-collect-alone
    Then the check names both modules

  Scenario: the collect-alone check runs no tests
    Given a test module whose tests would fail if run
    And that module collects on its own
    When the just check aggregate runs check-test-modules-collect-alone
    Then the check passes for that module without running its tests

  Scenario: a repository arms a check only after its tree passes it
    Given a repository whose tree has a test module that fails collection on its own
    When this rule is ratified
    Then that repository's just check aggregate does not yet run check-test-modules-collect-alone
    And it arms the check only once its tree passes it

  Scenario: a suite with no order dependence passes both checks
    Given every test module collects on its own and every product module imports first in a fresh interpreter
    When the just check aggregate runs check-test-modules-collect-alone and check-product-modules-import-first
    Then both checks pass
```

3. Because item 2 adds an H2 heading, the revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for it in the same change. Its `test` MAY be `"TODO"`, and its `reason` MUST name the work item filed to implement `check-test-modules-collect-alone` and `check-product-modules-import-first`. That item is distinct from bd-ib-vc6o5q, which removes the one cycle measured today and builds neither check.
