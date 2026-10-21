---
topic: oom-kill-named-on-stalled-outcome
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T23:37:47Z
---

## Proposal: A stalled run whose sandbox was OOM-killed names the OOM kill

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a factory run's sandbox container is killed for exceeding its memory limit, the progress watchdog later records the run as `stalled-no-progress`, and nothing on the dispatch result or the journal says that memory was the cause. The operator sees a stall and investigates the work. This proposal requires the dispatch result and the journal record of that outcome to name the OOM kill, the run id and the container's memory limit when the factory reports the kill. The outcome stays `stalled-no-progress` for every other rule of the watchdog section: it is not non-convergence, and it does not bounce the item.

### Motivation

Work-item bd-ib-7rnipp, whose `dod_gate` refused it twice on gmktec (runs 01M57RNA8HTV and 01M57SD4NT46) because no ratified clause states the OOM vocabulary its Definition of Done names. Its second assertion, that such a run is not counted as non-convergence and its item is not bounced, is already stated in "### Dispatcher progress watchdog" ("Not non-convergence") and in "## Scenario 172 — A stall-watchdog cancel is never non-convergence: a first cancel is released and recovered, a second rests for a human". Plan spec-implementation-lockstep R1 batch 12 routes the item here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher progress watchdog", add a paragraph immediately after the "**Not non-convergence.**" paragraph:

> **An OOM kill is named.** When the factory reports that the run's sandbox container was killed for exceeding its memory limit, the dispatch result and the journal record of the `stalled-no-progress` outcome MUST name the OOM kill, the run id, and the container memory limit the factory reports. A limit the factory does not report MUST be recorded as unobservable, never omitted or guessed. The outcome otherwise remains `stalled-no-progress` for every rule of this section. Scenario 234 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, add at the end of the file (tests/heading-coverage.json MUST gain an entry in the same revise):

## Scenario 234 — A stalled run whose sandbox was OOM-killed names the kill and the memory limit

```gherkin
Feature: Memory exhaustion is named, not hidden behind a stall
  As an operator triaging a stalled factory run
  I want the dispatch to say when the sandbox was OOM-killed
  So that I fix the memory limit instead of investigating the work

  Scenario: An OOM-killed sandbox is named on the stalled outcome
    Given a dispatched run whose sandbox container the factory reports OOM-killed with a memory limit
    When the progress watchdog records the run as stalled-no-progress
    Then the dispatch result and its journal record name the OOM kill, the run id and the memory limit
    And the item is not bounced to backlog and no non-convergence observation is recorded

  Scenario: An unreported memory limit is recorded as unobservable
    Given a dispatched run whose sandbox the factory reports OOM-killed without a memory limit
    When the progress watchdog records the run as stalled-no-progress
    Then the journal record names the OOM kill and records the memory limit as unobservable
```
