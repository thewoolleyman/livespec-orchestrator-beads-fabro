---
topic: watchdog-observes-its-run-by-id
author: claude-opus-5-5
created_at: 2026-10-13T09:40:18Z
---

## Proposal: The progress watchdog observes its bound run by id

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds an observation clause to contracts.md §"Dispatcher progress watchdog": once the Dispatcher has bound the dispatched run's id, every later watchdog poll observes that one run by its id and does not list the runs the Fabro server holds. Discovery before the id is bound is unchanged. The watchdog's existing verdicts are preserved: a terminal run, a stalled run and a run that has disappeared from the server are each still detected. A new scenario exercises the clause.

### Motivation

Work-item bd-ib-6pdigz (plan stall-watchdog-false-kills, epic bd-ib-laf735). The watchdog polls every 30 s by listing every run the factory server has ever held (`fabro ps -a --json`). Measured 2026-10-12 against hp-xubuntu:32276: that listing returned 1,605 runs in 9-17 s wall, about 1.3-1.5 CPU-seconds and 100 MB per call. Server-side filters did not help (`--label` 12-14 s; running-only 30 s), while a per-run `fabro inspect <id>` took 1.1-1.5 s, about 0.15 CPU-seconds and 36 MB. With 8 dispatches in flight about 9 listings ran at once, using roughly 0.9 GB on the dispatching host plus a full-store scan on the factory for each, and the cost grows with run history on an already saturated factory. bd-ib-6pdigz's dispatch (run 01M4RM6ZFCHXQCFP3J35YWR5EM) was refused at dod_gate because no ratified clause governs how the watchdog observes its run; v130's §"Dispatcher progress watchdog" governs what counts as progress and how a cancel routes, but not the observation mechanism. Placement: this is the Dispatcher's own wire behaviour toward its factory, so it belongs in this repository's contracts.md beside the watchdog it constrains, not in livespec core.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Dispatcher progress watchdog", insert the following paragraph immediately after the paragraph that begins `**Progress.**`:

```markdown
**Observing the run.** Until the Dispatcher has bound the dispatched run's
id, the watchdog MAY discover the run by listing the runs the factory
holds. Once the run's id is bound, every later watchdog poll MUST observe
that run by its id through a per-run read of the factory, and MUST NOT list
the runs the factory holds; the cost of a poll MUST NOT grow with the
factory's run history. A per-run read MUST still let the watchdog detect
each outcome it detects today: the run reaching a terminal state, the run
making no progress under the rule above, and the run no longer being held
by the factory. A per-run read that fails, or whose answer cannot be
interpreted, MUST NOT be read as the run having disappeared; it is an
unobservable poll, and the watchdog MUST treat it no differently from a
listing that could not be read. Scenario 173 in `scenarios.md` exercises
this paragraph.
```

In `SPECIFICATION/scenarios.md`, append:

```markdown
## Scenario 173 — The progress watchdog observes its bound run by id and never lists the factory's run history

```gherkin
Feature: The watchdog's poll cost does not grow with the factory's run history
  Scenario: A bound run is polled by id
    Given a dispatch whose run id the Dispatcher has bound
    When the watchdog polls the run
    Then the poll reads that run by its id from the factory
    And the poll does not list the runs the factory holds
  Scenario: Discovery before the id is bound is unchanged
    Given a dispatch whose run id the Dispatcher has not yet bound
    When the watchdog polls for the run
    Then it may list the runs the factory holds to discover the run
  Scenario: A terminal run is still detected
    Given a dispatch whose bound run reaches a terminal state
    When the watchdog polls the run by its id
    Then it reports the run's terminal state exactly as it does when it lists runs
  Scenario: A disappeared run is still detected
    Given a dispatch whose bound run the factory no longer holds
    When the watchdog polls the run by its id and the factory reports no such run
    Then it reports the run as disappeared from the server
  Scenario: A failed per-run read is not a disappearance
    Given a dispatch whose bound run is still held by the factory
    When a per-run read of the run fails or returns an answer the watchdog cannot interpret
    Then the watchdog does not report the run as disappeared
    And it treats the poll as unobservable
```
```

The heading-coverage map MUST gain an entry for the new `## Scenario 173` heading in the same change, owned by bd-ib-6pdigz with `test` set to `"TODO"` and a non-empty reason, per this repository's revise co-edit discipline. If another revision has taken Scenario 173 by the time this proposal is revised, the revise MUST renumber it to the next free number in the heading, the contract sentence and the coverage entry alike.
