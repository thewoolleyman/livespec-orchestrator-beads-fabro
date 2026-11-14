---
topic: a-factory-launch-refused-before
author: claude-opus-5-5
created_at: 2026-11-14T13:06:51Z
---

## Proposal: A launch refused before any run exists emits one span naming its refusal class

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a launch is refused before any factory run is created, whichever component refused it (the fleet launcher, the dispatch preamble or the Dispatcher's admission valve or pre-dispatch wall) emits, through a self-contained emitter that imports nothing from the dispatcher package, exactly one span named livespec.dispatch.launch_refused to service livespec-dispatcher. The span carries the repository, the work-item id, the refusal time and livespec.dispatch.refusal_class from a closed set with an explicit unclassified value. A whole-factory outage, in which every launch is refused, then reads as a count of refused launches by class rather than as an absence of runs.

### Motivation

Work item bd-ib-bvbfol (plan factory-run-yield, epic bd-ib-ft26pi, assertion 2). Its spec-change-tier record links this topic, a-factory-launch-refused-before, and grades the behaviour unstated against ## Bounded session waits and observable inventory. The terminal-span paragraph covers a dispatch that reaches a terminal state, and bd-ib-2h6cfl's failure spans key on fabro.failure.cause. Both need a dispatch or a run to exist. A launch refused before that emits nothing queryable.

Two whole-factory outages on 2026-11-14 were therefore invisible to every yield query:
- From 12:09:25Z, after #5270 (bd-ib-v7aftf), every launch failed its preflight with ModuleNotFoundError until the revert #5277.
- From 05:09Z to 08:47Z, the provider spend cap ended runs; a fleet-wide provider hold then refused new launches from about 07:49Z until it lifted at 08:47:34Z.
Both costs could only be reconstructed by reading ledger comments by hand. Spec-change-tier holds, which leave items 'NOT re-ticketed' with no run, are invisible the same way.

Effect on the track metric (PRs per repository per hour merged to main and green): none directly. It makes each outage's yield cost one query. Measure it as one Honeycomb query returning refused launches per hour by class for the next outage window.

In-flight alignment: default-align. It extends the terminal-span paragraph alongside bd-ib-faprof, bd-ib-yq7ugj (the-terminal-dispatch-span-carries) and bd-ib-2h6cfl (a-factory-run-s-terminal), and amends none of their sentences. Filed as a DRAFT for throughput-plans-coordinator's grade.

### Proposed Changes

**1. Pre-run launch refusals (`contracts.md` §"Bounded session waits and observable inventory").** Immediately after the terminal-span paragraph that ends "... an export failure MUST NOT fail, delay or alter the dispatch's recorded outcome.", insert:

> **A launch refused before any run exists.** When any launching component (the fleet launcher, the dispatch preamble, or the Dispatcher's admission valve or pre-dispatch wall) refuses to launch a work-item before any factory run is created for it, the refusing component MUST emit exactly one span named `livespec.dispatch.launch_refused` to service `livespec-dispatcher` for that refusal. It MUST emit it through a self-contained emitter that imports nothing from the dispatcher package and depends on no module whose import can fail in the refused launch: either a standalone emitter script that uses only the Python standard library, or the launcher shell posting to the telemetry collector's HTTP endpoint. A component inside the dispatcher package (the preamble, the admission valve or the pre-dispatch wall) MUST invoke that standalone emitter as a separate process. It MUST NOT import emitter code through the dispatcher package. A refusal caused by a failing import can then still be recorded. The fleet launcher emits for `preflight_import_error` and `preflight_refused`. The dispatch preamble and the Dispatcher's admission valve emit for `provider_limit`, `credential` and `capacity_hold`, whichever of them refuses. The Dispatcher's pre-dispatch wall emits for `spec_change_hold`. Whichever component refuses emits for `unclassified`. The span MUST carry `livespec.repository`, `work.item.id`, the refusal time and `livespec.dispatch.refusal_class`. It MUST also carry `livespec.dispatch.id` when a dispatch id was already assigned, and otherwise omit it and name it in `livespec.dispatch.unavailable_fields`. `livespec.dispatch.refusal_class` MUST be exactly one value of this closed set:
>
> - `preflight_import_error`: a launch preflight could not run, for example because a module it imports is absent.
> - `preflight_refused`: a launch preflight ran and refused the item.
> - `provider_limit`: a provider spend limit, usage limit or provider hold refused the launch.
> - `credential`: a credential the launch needs was absent or rejected.
> - `spec_change_hold`: the pre-dispatch wall refused a held spec-change-tier item.
> - `capacity_hold`: a WIP cap, repository hold or factory hold refused the launch.
> - `unclassified`: no class above matches.
>
> A value outside this set MUST NOT be emitted, and adding a class is a change to this paragraph. A refused launch that is later retried emits one span per refused attempt. A launch that does create a run emits no `livespec.dispatch.launch_refused` span. The receiver allowlist MUST admit `livespec.dispatch.refusal_class`. Emitting this span follows this section's bounded asynchronous telemetry rules: an export failure MUST NOT fail, delay or alter the refusal or any later dispatch.

**2. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — A launch refused before any run exists emits one span naming its refusal class

Feature: A whole-factory outage is countable by refusal class
  As an operator measuring the yield cost of a factory outage
  I want every launch refused before a run exists to emit one classified span
  So that one query counts refused launches per hour by class

  Scenario Outline: Each refusal family emits its class
    Given a work-item whose launch is refused before any factory run is created because <cause>
    When the refusing component records the refusal
    Then exactly one livespec.dispatch.launch_refused span is emitted to livespec-dispatcher
    And the span carries livespec.repository, work.item.id and livespec.dispatch.refusal_class <class>

    Examples:
      | cause                                                        | class                  |
      | the launch preflight cannot import a module it needs         | preflight_import_error |
      | the launch preflight runs and refuses the item               | preflight_refused      |
      | the provider credential is at its organisation spend limit   | provider_limit         |
      | a credential the launch needs is absent                      | credential             |
      | the pre-dispatch wall refuses a held spec-change-tier item   | spec_change_hold       |
      | the repository WIP cap is reached                            | capacity_hold          |
      | a refusal no class rule matches                              | unclassified           |

  Scenario: A preflight that cannot import a dispatcher module is still recorded
    Given the launch preflight cannot import a module it needs, and that module is part of the dispatcher package
    When the fleet launcher refuses the launch
    Then exactly one livespec.dispatch.launch_refused span with livespec.dispatch.refusal_class preflight_import_error is still emitted
    And emitting it imports nothing from the dispatcher package

  Scenario: A launch that creates a run emits no launch-refused span
    Given a work-item whose launch creates a factory run
    When the launching component records the launch
    Then no livespec.dispatch.launch_refused span is emitted for it

  Scenario: An export failure does not change the refusal
    Given a launch refused before any run exists while the telemetry receiver is unreachable
    When the refusing component records the refusal
    Then the refusal and its ledger record are unchanged
```

**3. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json`, and to `tests/heading-coverage-debt.json` when it lands as a TODO, in the same change.
