---
topic: guard-the-materialized-workflow-toml
author: claude-opus-5-5:factory-context-per-turn-reduction
created_at: 2026-10-31T09:33:11Z
---

## Proposal: The materialized workflow.toml stays inside the engine's size limit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize §"Self-contained plugin dispatch" with a paragraph that bounds the size of the materialized implement-work-item workflow.toml in two places. A build-time repository check fails when a representative materialization exceeds 471,859 bytes, 90 percent of Fabro's 524,288-byte workflow-file limit. A dispatch-time refusal stops any dispatch whose materialized workflow.toml exceeds 524,288 bytes before the work item is claimed. Both name the measured size and the limits. Add Scenario 279 to exercise the paragraph.

### Motivation

Work item bd-ib-37wvsk (plan bd-ib-raqyki, coordinator stop-the-line ruling 2026-10-30). The 524,288-byte limit is Fabro's own, and nothing in this repository noticed the margin shrinking. Measured by petri-factory-on-gmktec: the materialized workflow.toml was 461,263 bytes on v0.261.0, about 88 percent of the limit. On v0.261.1 it was 524,287 bytes for livespec-dev-tooling-2zii7l, which launched one byte under. bd-ib-dsprir, at 526,975 bytes, was refused at fabro-run with "workflow file workflow.toml is 526975 bytes; maximum is 524288" after its item had already been claimed. The cause was 8aa900989 (bd-ib-qbtf7s), which carried the publication scripts in a prepare step's env; it was reverted. A later control dispatch on v0.262.3 materialized 463,547 bytes. The spec-change tier classifier found no visible clause stating a size ceiling, a build-time size target, or a pre-claim refusal that names the measured size, and named this clause as the generalization target.

### Proposed Changes

In SPECIFICATION/contracts.md §"Self-contained plugin dispatch", insert the following paragraph immediately after the paragraph that begins "**The materialized workflow directory.**":

**The materialized workflow.toml stays inside the engine's size limit.** The engine refuses a workflow file larger than 524,288 bytes, and it refuses it at `fabro-run`, after the Dispatcher has claimed the item. This repository MUST therefore bound the size of the `workflow.toml` the Dispatcher materializes for the reserved `implement-work-item` workflow in two places. First, the `just check` aggregate MUST run the repository check `check-materialized-workflow-toml-size`. That check MUST materialize the bundled `implement-work-item` workflow for a representative dispatch through the same materialization code a real dispatch runs, with the launch overlay and prepare steps included and a goal of exactly 20,480 bytes (above the 16,684-byte goal of the largest measured dispatch, bd-ib-qbtf7s on v0.262.3). It MUST fail when the materialized `workflow.toml` exceeds 471,859 bytes, 90 percent of the engine's limit, printing the measured size, the 471,859-byte threshold and the 524,288-byte limit. It MUST pass otherwise, printing the measured size, so growth is visible before it fails. Second, before the Dispatcher claims the item, every dispatch MUST measure the `workflow.toml` it materialized. When that measurement exceeds 524,288 bytes, the Dispatcher MUST refuse the dispatch before any claim is written and before any Fabro run exists, as a journaled pre-run refusal whose stage names the measured size and the limit. The refusal MUST leave the item in the status it held before the dispatch, with no dispatch claim. The two bounds are independent: the build-time check MUST NOT be read as making the dispatch-time refusal unnecessary, because a dispatch's goal and overlay can exceed what the representative materialization measured. This paragraph governs the reserved workflow and every registered variant, per "A registered variant is the reserved workflow's peer, not its exception" below. Measured 2026-10-30 by petri-factory-on-gmktec: on v0.261.1 the materialized workflow.toml reached 524,287 bytes for livespec-dev-tooling-2zii7l, and bd-ib-dsprir, at 526,975 bytes, was refused at fabro-run after its claim. Scenario 279 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append:

## Scenario 279 — A materialized workflow.toml over the engine's limit is caught at build time and refused before claim

```gherkin
Feature: The materialized workflow.toml never reaches the engine over its size limit
  As the maintainer of a repository whose dispatches the factory runs
  I want workflow.toml growth caught before release and any overrun refused before claim
  So that no dispatch claims an item and then fails at fabro-run on the engine's file-size limit

  Scenario: The build-time check fails above 90 percent of the limit
    Given a build whose representative materialized workflow.toml is 471,860 bytes
    When the just check aggregate runs check-materialized-workflow-toml-size
    Then the check fails
    And its output names the measured size 471,860, the 471,859-byte threshold and the 524,288-byte limit

  Scenario: The build-time check passes at or below the threshold and prints the size
    Given a build whose representative materialized workflow.toml is 463,547 bytes
    When the just check aggregate runs check-materialized-workflow-toml-size
    Then the check passes
    And its output names the measured size 463,547

  Scenario: A dispatch whose materialized workflow.toml exceeds the limit is refused before claim
    Given a ready work item whose materialized workflow.toml for this dispatch is 526,975 bytes
    When the Dispatcher dispatches it
    Then the Dispatcher refuses the dispatch before any claim is written and before any Fabro run exists
    And the journaled refusal names the measured size 526,975 and the 524,288-byte limit
    And the work item keeps the status it held before the dispatch, with no dispatch claim
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 279 heading, whose `test` MAY be "TODO" with a reason naming work item bd-ib-37wvsk. It MUST NOT add an entry for §"Self-contained plugin dispatch", which is unchanged as a heading and already mapped.
