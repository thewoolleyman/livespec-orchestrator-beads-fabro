---
topic: a-factory-run-s-terminal
author: claude-opus-5-5
created_at: 2026-11-14T00:18:12Z
---

## Proposal: A factory run's failure span names its cause class from a closed set, and its run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every livespec-dispatcher span that carries fabro.failure.cause also carries fabro.run_id, livespec.dispatch.id and a new attribute livespec.dispatch.failure_class, drawn from a closed, named set of cause classes with an explicit unclassified value. fabro.failure.category keeps its existing retry vocabulary (Scenario 65), but the span renders the literal value unreported where the run reported none, never an empty value or the string None. The receiver allowlist admits the new attribute. With these fields a Honeycomb query can break a week's failed factory runs down by cause.

### Motivation

Work item bd-ib-2h6cfl (held at the spec-change tier for this topic; plan factory-run-yield, epic bd-ib-ft26pi, assertion 2). The 2026-11-13 throughput report (ci-runtime-and-cost) counted 406 of 788 ended factory runs as failed in 7 days (Honeycomb query kurpKF7PJY6). It could not break them down by cause: 52% of the ended Petri runs' failure spans carry the string 'None' as fabro.failure.category and no fabro.run_id. Scenario 12 and contracts.md §"Calibration telemetry and the single Fabro tweak" state only that an outcome class is written to the journal. Nothing states a cause vocabulary, its closedness, or the run correlation on the failure span, so the spec-change-tier judgement graded the item PARTIAL against Scenario 12. DESIGN CHOICE: the cause set is a NEW attribute rather than a new meaning for fabro.failure.category. That attribute already carries Fabro's retry-semantics vocabulary (transient_infra, permanent, deterministic), and Scenario 65 classifies on it, so overloading it with cause classes would change routing. The track metric is PRs per repository per hour merged to main and green. This proposal adds no PRs directly. It is the measurement that ranks the yield levers: each 10 points of factory yield at the same run count is about 79 more factory PRs a week. In-flight alignment: default-align. No open spec pull request touches failure-span telemetry (surveyed 2026-11-14). When this ratifies, bd-ib-2h6cfl's Definition of Done must name livespec.dispatch.failure_class where it now names fabro.failure.category as the closed set. That is a regroom of the item, recorded on plan factory-run-yield.

### Proposed Changes

**1. Failure-span cause class (`contracts.md` §"Calibration telemetry and the single Fabro tweak").** After the numbered list, add:

> **Failure cause class.** When a factory run ends in a terminal failure, every span the Dispatcher emits to service `livespec-dispatcher` that carries `fabro.failure.cause` MUST also carry `fabro.run_id` naming the failed run and `livespec.dispatch.id` naming its dispatch. It MUST also carry `livespec.dispatch.failure_class`, set to exactly one value of the closed cause-class set below. The Dispatcher derives the class from the run's recorded failure cause, its failing node and its failure detail, and from nothing else. The set and its matching rules MUST live in ONE committed table in the plugin, and every emitter MUST read that table. The set, in matching precedence order:
>
> - `canceled`: the run was cancelled.
> - `provider_limit`: the failure detail carries the typed provider-limit flag (Scenario 65).
> - `unprovable_assertion`: `proof_capture` ended because a `factory_captured` assertion's proof surface was not available in the sandbox, including the missing-capability ending.
> - `script_timeout`: a refresh, janitor or gate script exceeded its time bound.
> - `rebase_conflict`: the run's rebase onto its target branch stopped on a conflict.
> - `open_red_bound_exhausted`: `review_fix` exhausted its open-Red re-entry bound.
> - `gate_check_failed`: a gate check inside the run exited non-zero for a reason other than a timeout.
> - `unclassified`: no rule above matches.
>
> A value outside this set MUST NOT be emitted. Adding a class is a change to this clause. `fabro.failure.category` keeps the vocabulary the run reports and that Scenario 65 governs. Where the run reported no category, the span MUST carry the literal value `unreported`, and MUST NOT carry an empty value or the string `None`. That rendering is span-only and MUST NOT change any routing that reads the category. The receiver allowlist (`_otel_scrub.ATTRIBUTE_ALLOWLIST`) MUST admit `livespec.dispatch.failure_class`. Emitting these attributes follows the bounded asynchronous telemetry rules: an export failure MUST NOT fail, delay or alter the dispatch's recorded outcome.

**2. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — A factory run's failure span names its cause class from a closed set, and its run

Feature: Failed factory runs are countable by cause
  As an operator reading a week of failed factory runs
  I want every failure span to name its run and a closed cause class
  So that a breakdown by cause has no empty or None group

Scenario Outline: Each measured cause maps to its own class
  Given a factory run that ended in a terminal failure whose recorded cause is <cause>
  When the Dispatcher emits the span carrying fabro.failure.cause
  Then the span carries livespec.dispatch.failure_class <class>
  And the span carries the failed run's fabro.run_id and livespec.dispatch.id

  Examples:
    | cause                                                         | class                    |
    | proof capture could not exercise a factory_captured assertion | unprovable_assertion     |
    | a refresh, janitor or gate script timed out                   | script_timeout           |
    | the rebase onto the target branch stopped on a conflict       | rebase_conflict          |
    | a gate check exited non-zero                                  | gate_check_failed        |
    | review_fix exhausted its open-Red bound                       | open_red_bound_exhausted |

Scenario: A cause no rule matches is unclassified, never empty
  Given a failed run whose recorded cause matches no rule of the cause-class table
  When the Dispatcher emits the failure span
  Then livespec.dispatch.failure_class is unclassified

Scenario: A run that reported no category renders unreported
  Given a failed run whose Fabro failure carries no category
  When the Dispatcher emits the failure span
  Then fabro.failure.category is unreported rather than empty or None
  And the Dispatcher's routing on that run is unchanged
```

**3. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change.
