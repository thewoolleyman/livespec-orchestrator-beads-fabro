---
topic: a-fork-test-s-verdict-never
author: claude:fabro-currency session e3e56105
created_at: 2026-11-12T17:55:44Z
---

## Proposal: A fork test's verdict never depends on host load or wall-clock time

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Codify the maintainer's standing ruling of 2026-11-03 as one clause under the "Fork gate and build venue" bullet of constraints.md §"Fabro runtime constraints". The only time bound on a test in the fork's carrier tree is the overall run timeout. No fork test may place a test-local wall-clock deadline in front of the state or event it waits for. A test that fails on load or timing is a test defect, tracked as a root-fix item, and a rerun pass, retry, skip, ignore or longer deadline is never its resolution. No new design: the rule exists and is enforced today, but only in `.ai/fabro-fork-hand-build.md`.

### Motivation

The maintainer ruled on 2026-11-03, as recorded in `.ai/fabro-fork-hand-build.md` §"A test verdict never depends on load": "a test's verdict must never depend on host load or wall-clock time. The only time bound is the overall run timeout (locally, in the factory and in CI). A test that genuinely hangs is a separate bug." The same section records the consequences the fleet already follows. A test that fails or times out on load or timing is a TEST DEFECT, filed once as a root-fix item. "Retries, skips, `#[ignore]` and longer deadlines are not fixes." And "a rerun pass is not evidence."

That file is the rule's only carrier, and it is not part of the governed spec tree. So the spec-change-tier classifier, which grades a Definition of Done against the ratified spec, reads every fork test-defect item as unstated behaviour and holds it at spec-change tier. Measured 2026-11-12 on bd-ib-3edyng (the fabro-cli worker_auth helpers: a 5 s `wait_for_http_ready` bound and two 30 s `COMMAND_TIMEOUT` deadlines, which failed Fork gates run 43264542247 on factory-integration 93081e09d, a tree byte-identical to the green-gated d22808f8e). classify-tier returned `tier: spec-change`, `verdict-kind: partial`, rationale "The spec says nothing about the fork's worker_auth test helpers waiting on observed state instead of wall-clock deadlines". It returned that even after the item's Definition of Done was reduced to the one ratified Fork-gates clause and dod-preflight passed. Earlier items of the same class (bd-ib-sltfyg, bd-ib-4uge7u, bd-ib-gmuxd4) tiered `none` only because they predate the verdict-taking classifier. So every new fork test-defect item now stalls at this tier.

The fleet coordinator (legacy-coordinator-agent, ~18:0xZ 2026-11-12) gave GO to codify the ruling here as a one-clause proposal. It takes the orchestrator revise slot right after the-factory-graph-gate-validates. On ratification the coordinator releases bd-ib-3edyng's tier against this clause.

FLEET SCOPE: the clause binds every test file in the fork's carrier tree (`thewoolleyman/fabro`, any branch a pinned factory build is cut from, together with the Petri fork tree that carrier locks). That includes bd-ib-3edyng's two 30 s `COMMAND_TIMEOUT` deadlines beside its 5 s readiness bound. It governs only the fork, which is the factory's engine; it adds nothing for adopter repositories or this repository's own Python suite.

### Proposed Changes

### 1. `SPECIFICATION/constraints.md` §"Fabro runtime constraints": extend the "Fork gate and build venue" bullet

Append these sentences to the end of the bullet, after "...names the cluster venue, under the runbook-lockstep rule below.":

```markdown
  A test's verdict in the fork's carrier tree MUST NOT depend on host load
  or wall-clock time: the only time bound on a fork test is the overall
  run timeout of the run that executes it (locally, in the factory and in
  CI), and a fork test MUST NOT place a test-local wall-clock deadline in
  front of the state or event it waits for. A fork test that fails or
  times out on load or timing is a test defect, tracked as a root-fix
  work-item; a rerun pass, a retry, a skip, an ignore marker or a longer
  deadline MUST NOT be recorded as its resolution. This codifies the
  maintainer's ruling of 2026-11-03, whose operating detail the
  hand-build guidance carries.
```

No other sentence of the bullet changes.

### 2. `SPECIFICATION/scenarios.md`: add one scenario after the last existing scenario

The heading is numberless here; the revise pass assigns the next free scenario number.

~~~markdown
## Scenario: a fork test waits on the state it needs, never on the clock

```gherkin
Feature: A fork test's verdict never depends on host load or wall-clock time
  As the maintainer of the fork the factory runs on
  I want fork tests to decide on the state they observe
  So that a loaded runner can never turn a healthy test red

  Scenario: A loaded runner delays the awaited state and the test still decides on it
    Given a test in the fork's carrier tree that waits for a server to become ready, a directory to appear or an event to arrive
    And the runner executing it is loaded so that the awaited state arrives later than usual
    When the test runs
    Then its verdict is decided by the awaited state or by the overall run timeout
    And no test-local wall-clock deadline expires first

  Scenario: A timing failure is tracked as a test defect, not cleared by a rerun
    Given a fork gate reports a test that failed on a test-local wall-clock deadline
    When the failure is dispositioned
    Then it is tracked as a root-fix test-defect work-item
    And no rerun pass, retry, skip, ignore marker or longer deadline is recorded as its resolution
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

Add one entry to `tests/heading-coverage.json`, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a fork test waits on the state it needs, never on the clock", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "A real test at the scenario tier or above is owed for this heading: the thewoolleyman/fabro fork's worker_auth integration tests wait on server readiness, the run directory and completed events by observing those states, proved on a Fork gates Test run of the carrier branch carrying the fix, together with a mutation check that each still fails when its behaviour is removed. bd-ib-3edyng owns it.", "work_item": "bd-ib-3edyng"}
```

Add the matching row to `tests/heading-coverage-debt.json`, as `check-heading-coverage-debt-register` requires:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a fork test waits on the state it needs, never on the clock", "work_item": "bd-ib-3edyng", "first_seen": "<revise date>"}
```

The revise that ratifies this MUST co-edit both files, per AGENTS.md §"Revise co-edit discipline". No existing heading changes.

### 4. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-3edyng's tier is re-classified against the extended bullet and released by the coordinator. `.ai/fabro-fork-hand-build.md` §"A test verdict never depends on load" then gains a line naming this clause as the rule's ratified carrier.
