---
topic: the-dispatcher-command-modules-form
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-12T05:49:52Z
---

## Proposal: Every test module collects and runs when selected on its own, and every product module imports first

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

A full-suite run can hide an import cycle among product modules. The suite collects because some earlier module happens to import the cycle's members in a working order, so a test module that imports a cycle member first fails collection only when it is selected on its own. A factory implement turn's targeted Red-Green run selects exactly that way. This proposal adds one forbidden pattern to constraints.md, beside the existing rule against real-time sleeps in tests. Every test module under `tests/` MUST collect and run when pytest selects it on its own, whatever order the rest of the suite would import modules in. Every product module of the plugin package MUST import successfully as the first plugin module in a fresh interpreter. The `just check` aggregate MUST enforce both through two named checks. One new un-numbered scenario exercises the rule.

### Motivation

Owning work item bd-ib-vc6o5q, "The Dispatcher command modules form an import cycle through _dispatcher_fabro_reattach, so a test that imports the reattach module first fails collection and blocks every targeted Red-Green run on it". At filing and again at 05:47:25Z on spec v358, its classify-tier judgement read partial and held it for this topic: "The ratified text does not state the main requirement, that the reattach coverage module collects and passes when run alone. That is an internal import-structure property, and no visible clause covers it." legacy-coordinator-agent routed this topic, generalized, as a real rule worth having (2026-11-12 about 05:55Z).

Measured on master 97fe667b0: `pytest --collect-only` on tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reattach_watch_coverage.py alone fails with "ImportError: cannot import name 'ReattachRun' from partially initialized module 'livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach' (most likely due to a circular import)". The cycle runs `_dispatcher_fabro_reattach` -> `_dispatcher_run_watch_decision` -> `_dispatcher_stall_cancel` -> `_dispatcher_engine` -> `_dispatcher_post_run_terminal` -> `_dispatcher_fabro_reattach`, and fdcbefbb9 (bd-ib-pxp2ve) introduced it. Master CI stays green because the full suite imports the engine first. The cost landed on bd-ib-ag633q: its FRESH run 01M772057DRH spent two implement turns and rested at needs-human with empty diffs after its targeted run hit the collection failure. Nothing in the aggregate notices this class today.

Placement: this is a contributor-facing rule about this repository's own test suite and product package, enforced by its own `just check` aggregate, exactly as the neighbouring "No real-time sleeps or wall-clock verdicts in tests" bullet is. So it belongs in constraints.md §"Forbidden patterns". Fleet scope: the same order-dependent collection can hide in every fleet repository whose CI collects only the full suite. The two checks are named here so that livespec-dev-tooling can ship them as canonical shared checks for the fleet. That shared realization is a livespec-dev-tooling deliverable, not part of this repository's requirement.

In-flight survey: the open spec PRs #5005 (a-needs-human-rest-overwrites) and #4999 (revise plan-record-artifact-paths-include-imported-code) and the pending in-tree proposals touch no part of §"Forbidden patterns". Nothing to align with.

### Proposed Changes

1. constraints.md, §"Forbidden patterns": IMMEDIATELY AFTER the bullet that begins "- No real-time sleeps or wall-clock verdicts in tests." (which ends "for a test whose subject is real time itself."), insert this bullet as the section's next list item:

"- No order-dependent test collection or product-module import. Every test module under `tests/` MUST collect, and its tests MUST run, when pytest selects that module on its own in a fresh process, whatever order the rest of the suite would import modules in. Every product module under `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/` MUST import successfully as the first module of that package in a fresh interpreter. An import cycle among product modules that resolves only because some other module was imported first violates both rules. The `just check` aggregate MUST enforce them through two checks. `check-test-modules-collect-alone` MUST collect each test module under `tests/` in its own pytest process and MUST refuse naming each module that fails collection and its error. `check-product-modules-import-first` MUST import each product module first in its own fresh interpreter and MUST refuse naming each module that fails to import and its error. Either check MAY run its modules in parallel, and MUST report every failing module rather than stopping at the first."

No other bullet of the section changes.

2. scenarios.md: append one new H2 section at the end of the file, after the last existing section, separated from it by one blank line:

## Scenario: a test module or product module that works only after another import is refused by the aggregate

```gherkin
Feature: a test module or product module that works only after another import is refused by the aggregate

  Scenario: a test module that fails collection on its own is refused
    Given product modules A and B import each other at module level
    And the full test suite collects because an earlier test module imports B before A
    And test module T imports A before any other product module
    When the just check aggregate runs check-test-modules-collect-alone
    Then the check refuses
    And it names T and its collection error

  Scenario: a product module that fails to import first is refused
    Given product modules A and B import each other at module level, so that importing A first fails
    When the just check aggregate runs check-product-modules-import-first
    Then the check refuses
    And it names A and its import error

  Scenario: every failing module is reported
    Given two test modules that each fail collection on their own
    When the just check aggregate runs check-test-modules-collect-alone
    Then the check names both modules

  Scenario: a suite with no order dependence passes both checks
    Given every test module collects on its own and every product module imports first in a fresh interpreter
    When the just check aggregate runs check-test-modules-collect-alone and check-product-modules-import-first
    Then both checks pass
```

3. Because item 2 adds an H2 heading, the revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for it in the same change. Its `test` MAY be `"TODO"`, and its `reason` MUST name the work item filed to implement `check-test-modules-collect-alone` and `check-product-modules-import-first`. That item is distinct from bd-ib-vc6o5q, which removes the one cycle measured today and builds neither check.
