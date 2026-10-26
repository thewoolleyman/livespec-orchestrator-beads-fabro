---
topic: fabro-dump-shared-timeout
author: claude-opus-5-5
created_at: 2026-10-26T11:32:21Z
---

## Proposal: One shared bound for every Dispatcher fabro dump, sized from the slowest factory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Every `fabro dump` the Dispatcher runs to read a run's record (the preserve-by-reference export, its read-back check, and the worker-exit log read) is bounded by one shared timeout whose value is sized from measured dumps on the slowest participating factory: 900 seconds today.

### Motivation

The Dispatcher bounds each of its three `fabro dump` call sites with its own private 300-second constant, and no ratified heading governs that bound or its value, so work-item bd-ib-exyiqr (raise the bound) failed its pre-dispatch governing-heading screen. Measured on the petri factory on 2026-10-26, Dispatcher dumps timed out at 300 s (exit 124) for three runs: 01M5V3R83PN3 (bd-ib-ltfh5p, 09:30:51Z), 01M5V5KVG8J7 (bd-ib-od7v54, 10:01:29Z) and 01M5V4W79JWJ (bd-ib-uk3fop, 08:23:57Z). A by-hand dump of the uk3fop run finished within a 600-second bound with a 159 MB events.jsonl, and a by-hand dump of run 01M5V7TME9S4 (bd-ib-hfi52b) took 465 s. A dump that times out turns an export that would have carried the run's diff digest into a dump-failed pointer, so the bound decides whether a needs-human ending preserves a digested reference to the run's work. 900 s is about twice the measured maximum. Coordinator ruling R27 (recorded on livespec-dev-tooling-dfixhe) directed this change spec-first.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher policy settings" → "A factory run never awaits a human", insert one new bullet immediately after the bullet that ends "The export is the precondition, not a courtesy: a termination whose export was not read back MUST NOT proceed.":

```
- Every `fabro dump` the Dispatcher runs to read a run's record — the
  export behind a preserve-by-reference pointer, the read-back that checks
  that pointer, and the read of a worker-exit log — MUST be bounded by ONE
  shared timeout, the same value at every such call site, so that no call
  site gives up on a dump another would have completed. The value MUST be
  sized from measured dump durations on the slowest factory declared under
  `dispatcher.factories`, with headroom of about twice the measured
  maximum; it is 900 seconds. A dump that completes within the bound MUST
  yield the same pointer as any completed dump, carrying the run's diff
  digest when the export holds a diff artifact. A dump that exceeds the
  bound is a failed dump: the pointer MUST record the failure and its exit
  code, and MUST NOT claim a digest. Measured 2026-10-26 on the petri
  factory, three Dispatcher dumps timed out at a 300-second bound, while a
  dump of the same size finished within 600 seconds and another took 465
  seconds. Scenario 247 in `scenarios.md` exercises this bullet.
```

2. In `SPECIFICATION/scenarios.md`, append after Scenario 246:

```
## Scenario 247 — Every Dispatcher fabro dump shares one bound sized from the slowest factory

```gherkin
Feature: The Dispatcher waits for a slow factory's dump before giving up on it
  Scenario: A dump slower than ten minutes still yields a digested pointer
    Given a run whose export holds a diff artifact
    And the factory takes 700 seconds to complete the run's fabro dump
    When the Dispatcher writes the run's preserve-by-reference pointer
    Then the dump completes within the bound
    And the pointer carries the run's diff digest
  Scenario: A dump past the bound is a failed dump
    Given a run whose fabro dump has not completed after 900 seconds
    When the Dispatcher writes the run's preserve-by-reference pointer
    Then the dump is stopped at the bound
    And the pointer records the failed dump and its exit code
    And the pointer claims no digest
  Scenario: Every call site uses the same bound
    Given the preserve-by-reference export, its read-back check and the worker-exit log read
    When each runs a fabro dump
    Then each dump is bounded by the same 900-second timeout
```
```

3. In `tests/heading-coverage.json`, append one entry: `heading` "## Scenario 247 — Every Dispatcher fabro dump shares one bound sized from the slowest factory", `spec_root` "SPECIFICATION", `spec_file` "scenarios.md", `test` "TODO", `reason` "Bound by the implementing work-item bd-ib-exyiqr, which replaces the three private 300-second dump constants with one shared 900-second constant."
