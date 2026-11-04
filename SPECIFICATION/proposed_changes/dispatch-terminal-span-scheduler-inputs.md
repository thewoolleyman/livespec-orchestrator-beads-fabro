---
topic: dispatch-terminal-span-scheduler-inputs
author: claude-opus-5-5
created_at: 2026-11-04T19:30:22Z
---

## Proposal: The terminal dispatch span carries the run class, the execution target and its sandbox's CPU-seconds and peak memory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the `livespec.dispatch.terminal` span paragraph in contracts.md §"Bounded session waits and observable inventory" so the terminal span also carries `livespec.dispatch.run_class`, `livespec.dispatch.execution_target`, `livespec.sandbox.cpu_seconds` and `livespec.sandbox.memory_peak_bytes`, under the paragraph's existing omit-and-name rule for unobservable values and its allowlist rule, and add one scenario.

### Motivation

The livespec-dev-tooling plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3), plan assertion 9: "Every factory run emits one terminal span to Honeycomb carrying the run id, the work item id, the execution target, the run class, start and end time, outcome, CPU-seconds and peak memory of its sandbox, and those keys are in the orchestrator's OTel attribute allowlist". That plan's radar admission function places work by each run class's measured p90 CPU-seconds and peak memory per execution target, read from Honeycomb by code (livespec-dev-tooling SPECIFICATION/non-functional-requirements.md §"Scheduler Honeycomb input contract"), and nothing emits those per-run figures today. The terminal span is being built by bd-ib-welwbc (relay R3 from plan factory-spend-accuracy); a coordinator ruling (R301, 2026-11-02) carries the four attributes as an EXTENSION of that span, never as a parallel span, and leaves welwbc's own Definition of Done unchanged, so the implementation item for this proposal takes a blocks edge on welwbc. Run id, work item id, outcome and timing are already carried by the terminal span and its dispatch-span parent. The realization belongs in this repository's spec because the Dispatcher and its receiver allowlist are this orchestrator's mechanism. Open spec branches surveyed 2026-11-04 (dispatch pre-launch steps, re-dispatch after needs-human, fabro rm deletions, DoD judgement at the dispatch wall) touch dispatch lifecycle, not span attributes, and are default-aligned.

### Proposed Changes

1. In `SPECIFICATION/contracts.md` §"Bounded session waits and observable inventory", in the paragraph that begins "When a dispatch reaches a terminal state, the Dispatcher MUST emit exactly one terminal span named `livespec.dispatch.terminal`", insert after the sentence that requires `livespec.dispatch.attempt_count`:

The terminal span MUST also carry these four attributes, which the radar admission function of livespec-dev-tooling reads to place work by measured cost:

- `livespec.dispatch.run_class`, the name of the Fabro workflow the dispatch ran, such as `implement-work-item`;
- `livespec.dispatch.execution_target`, the host name of the machine whose capacity the run's sandbox consumed. For a Kubernetes pod sandbox this MUST be the host that the pod's `k8s.node.name` runs on;
- `livespec.sandbox.cpu_seconds`, the total CPU time the run's sandbox consumed over the dispatch, in seconds, as a non-negative number read from the sandbox's control group;
- `livespec.sandbox.memory_peak_bytes`, the peak memory of the run's sandbox over the dispatch, in bytes, as a non-negative integer read from the sandbox's control group.

These four follow the same omit-and-name rule as every other value in this paragraph: a value the Dispatcher cannot observe MUST be omitted, never fabricated or written as zero, and named in `livespec.dispatch.unavailable_fields`. The receiver allowlist MUST admit all four.

2. Add to `SPECIFICATION/scenarios.md` a new scenario:

## Scenario 309 — A terminal dispatch span carries its run class, execution target and sandbox cost

```gherkin
Feature: Terminal dispatch span cost attributes
  As the radar admission function placing work by measured cost
  I want each terminated dispatch to report where it ran and what its sandbox consumed
  So that per-run-class cost percentiles can be read from Honeycomb by code

  Scenario: An implement-work-item dispatch whose pod sandbox ran on gmktec-xubuntu terminates
    Given an implement-work-item dispatch whose pod sandbox was scheduled on a node of gmktec-xubuntu and consumed 840 CPU-seconds with a memory peak of 3221225472 bytes
    When the dispatch terminates
    Then its livespec.dispatch.terminal span carries livespec.dispatch.run_class implement-work-item and livespec.dispatch.execution_target gmktec-xubuntu
    And it carries livespec.sandbox.cpu_seconds 840 and livespec.sandbox.memory_peak_bytes 3221225472
    And all four keys survive the receiver allowlist into dataset livespec-dispatcher

  Scenario: A dispatch whose sandbox control group cannot be read
    Given a dispatch whose sandbox control group was gone before its usage was read
    When the dispatch terminates
    Then its terminal span MUST NOT carry livespec.sandbox.cpu_seconds or livespec.sandbox.memory_peak_bytes
    And livespec.dispatch.unavailable_fields on that span names both
```

## Proposal: A check fails when a change drops an attribute that livespec-dev-tooling's scheduler query specs require

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to contracts.md §"Bounded session waits and observable inventory" requiring a `just check` member that reads livespec-dev-tooling's published `required_columns.json` from the pinned livespec-dev-tooling package and fails when an attribute it requires of this repository's spans is missing from the receiver allowlist or from this repository's declared emitted-attribute vocabulary, and add one scenario.

### Motivation

The livespec-dev-tooling plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3), plan assertion 10: "A gate on master in the orchestrator repository fails when a change removes or renames an emitted attribute, or drops an allowlist key, that a query spec in the contract depends on; the contract's required attribute set is read by that gate from one committed file, not duplicated." livespec-dev-tooling SPECIFICATION/non-functional-requirements.md §"Scheduler Honeycomb input contract" already requires that set to be "published from one committed file that other repositories' gates read, never duplicated"; livespec-dev-tooling-k3dpo2 generates it as `required_columns.json`. This repository already consumes livespec-dev-tooling as a tag-pinned package (pyproject.toml), so the check reads the file from the installed pin and performs no network I/O, and a requirement change reaches this check only through the ordinary pin bump. Without the check, a rename in an emitter or a trimmed allowlist silently starves the admission function of an input, and the scheduler falls back without anyone seeing why. Placed in this repository's spec because the receiver allowlist and the emitters are this orchestrator's mechanism. The implementation item is blocked until a livespec-dev-tooling release carrying `required_columns.json` exists and this repository's pin is bumped to it; the requirement carries no exemption for that window, because arming a check before the file it reads exists is the ordering this fleet has paid for.

### Proposed Changes

1. Add to `SPECIFICATION/contracts.md` §"Bounded session waits and observable inventory", after the paragraph on the terminal dispatch span, this paragraph:

**Attributes a downstream scheduler requires.** livespec-dev-tooling publishes, in its package, one generated file `required_columns.json` naming every attribute and column its scheduler query specs read, each with the dataset it is read from. This repository MUST declare every span attribute key its emitters write in one committed emitted-attribute vocabulary module, and every emitter MUST take its keys from that module. A member of `just check` MUST read `required_columns.json` from the livespec-dev-tooling package this repository pins, and MUST fail, naming the attribute and its dataset, when an attribute the file requires from a dataset this repository's emitters write to (`livespec-dispatcher`, and the datasets the factory's step and turn spans reach) is absent from the emitted-attribute vocabulary or absent from `_otel_scrub.ATTRIBUTE_ALLOWLIST`. The check MUST read the required set only from that file and MUST NOT keep a second copy of it. It MUST perform no network I/O. A change to the required set MUST reach this check only through a bump of the livespec-dev-tooling pin.

2. Add to `SPECIFICATION/scenarios.md` a new scenario:

## Scenario 310 — Dropping an attribute the scheduler requires fails the check

```gherkin
Feature: Scheduler-required attribute check
  As the maintainer relying on the radar admission function's Honeycomb inputs
  I want a change that drops or renames a required attribute to fail before it merges
  So that the scheduler is never silently starved of an input

  Scenario: A change renames a required terminal-span attribute
    Given the pinned livespec-dev-tooling package's required_columns.json requires livespec.sandbox.cpu_seconds from dataset livespec-dispatcher
    When a change renames that key in the emitted-attribute vocabulary to livespec.sandbox.cpu_s
    Then just check MUST fail naming livespec.sandbox.cpu_seconds and dataset livespec-dispatcher

  Scenario: A change drops a required key from the receiver allowlist
    Given the same required_columns.json
    When a change removes livespec.sandbox.cpu_seconds from _otel_scrub.ATTRIBUTE_ALLOWLIST
    Then just check MUST fail naming livespec.sandbox.cpu_seconds and dataset livespec-dispatcher
```
