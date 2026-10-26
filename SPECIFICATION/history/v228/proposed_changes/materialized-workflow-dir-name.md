---
topic: materialized-workflow-dir-name
author: claude-opus-5-5
created_at: 2026-10-26T17:43:55Z
---

## Proposal: The materialized workflow directory name is dot-free and distinct per work-item id

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Under Self-contained plugin dispatch, the directory the Dispatcher materializes for a dispatch's workflow copy is named so the engine resolves it for every valid work-item id: the name contains no '.', and the id-to-name mapping is injective, so ids differing only by a dot never share a directory.

### Motivation

Coordinator gitops-fleet-capacity-monitoring ruling R40 (high priority, it blocks a breakage fix) routes this spec-first change so work-item bd-ib-5y25l2 has a governing clause; its screen split at 17:02Z because no clause governs the materialized workflow directory's name. _dispatcher_loop_plan.py:101 names that directory fabro-workflow-{work_item_id}, and the Fabro client refuses a directory whose name contains a dot ("failed to resolve local workflow ... workflow not found"), so the dispatch dies at stage fabro-run before any run exists. Measured 2026-10-26 with the petri client (carrier-petri-v0.382-adeefec4c): overseer-uzvcbn.6 failed this way on two launches (14:40Z on 0.243.7, 16:35Z on 0.243.8). Control: two byte-identical copies of a working materialized workflow directory, named wf-plain and wf-dotted.6, returned "Validation: OK" and "workflow not found" respectively under fabro validate, so the directory name alone decides. Nine dotted items across this repository and livespec-overseer are stuck, including bd-ib-nmuyjc.1 and .2.

The clause fixes the required properties (dot-free, injective) rather than a scheme, as the coordinator asked. Injectivity is load-bearing: the obvious fix of replacing "." with "-" would collide "x.2" with "x-2", and the scenario's second case guards that.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", insert a new paragraph immediately after the "Target-local workflow" paragraph, which ends:

```
registered variant. The resolved committed path MUST be journaled on
the dispatch record as `workflow_toml`.
```

so that it is followed by:

```
**The materialized workflow directory.** When the Dispatcher materializes a
per-dispatch copy of the resolved workflow for the engine to run, the name of
the directory it materializes MUST be one the engine resolves as a local
workflow for every valid work-item id. The name MUST contain no `.` character,
whatever characters the work-item id contains, and the mapping from work-item
id to directory name MUST be injective, so two distinct work-item ids,
including two that differ only where one has a `.` and the other another
character, never share a materialized directory. This paragraph fixes those
properties, not an encoding scheme. The `workflow_toml` journal field keeps
naming the resolved committed path, never the materialized copy. Measured
2026-10-26 with the petri Fabro client: two byte-identical copies of a working
materialized workflow directory, named `wf-plain` and `wf-dotted.6`, returned
`Validation: OK` and `workflow not found` respectively under `fabro validate`,
and every work item whose id contains a dot, which includes every dotted plan
child, failed at `fabro-run` before any run existed. Scenario 250 in
`scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 250 — A work item whose id contains a dot dispatches from a dot-free workflow directory distinct to its id

```gherkin
Feature: A work-item id never decides whether the engine can find its workflow
  As the maintainer of a repository whose plan children carry dotted ids
  I want every work item to dispatch whatever characters its id contains
  So that a dotted plan child is not stranded at fabro-run before any run exists

  Scenario: A dotted work-item id dispatches
    Given a ready work item whose id is "bd-ib-abc123.2"
    When the Dispatcher materializes the workflow for its dispatch
    Then the materialized directory name contains no "." character
    And the engine resolves that directory as a local workflow
    And the journal's workflow_toml names the resolved committed path

  Scenario: Ids that differ only by a dot get distinct directories
    Given two work items whose ids are "bd-ib-abc123.2" and "bd-ib-abc123-2"
    When the Dispatcher materializes the workflow for each dispatch
    Then the two materialized directory names differ
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-5y25l2.
