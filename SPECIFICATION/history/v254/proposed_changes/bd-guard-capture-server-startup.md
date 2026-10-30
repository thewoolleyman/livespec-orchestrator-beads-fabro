---
topic: bd-guard-capture-server-startup
author: claude-opus-5-5
created_at: 2026-10-29T16:39:35Z
---

## Proposal: The lifecycle guard's test harness waits for its telemetry capture server on a bounded, diagnosable start

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add one constraint bullet under 'Beads substrate constraints' and one new scenario that govern how the lifecycle guard's (bd-guard) test harness starts the throwaway telemetry capture server its OTLP cases use. The harness MUST wait until the server publishes its port file, the server process exits, or a 30-second bound elapses, whichever comes first. A start that takes longer than two seconds MUST NOT fail a case. A server that does not start MUST produce a failure line naming the server's exit status and its captured standard error.

### Motivation

Work item bd-ib-qbwd7n: inside a factory janitor aggregate on a loaded host (run 01M515AA906VCTAFFZ5JRAJJKX, janitor@2, 2026-10-16), check-bd-guard reported 'telemetry: capture server did not start (9.1)' once. The same tree was green in every other observed run. bd-guard/test/run-tests.sh start_capture polls a fixed 40 x 0.05 s (two seconds) for the port file and, on expiry, fails without saying whether the server was slow, failed to bind, or was reaped. The work item cannot be dispatched because no spec text governs the harness: Scenario 52 covers only resolving the bd entry point, and SPECIFICATION/*.md never mentions the guard's telemetry or its test harness. Its launch screen (petri-factory-on-gmktec, 2026-10-29) returned governing-heading kind 'unstated'. This proposal supplies the governing clause and scenario, and the item's References line will name the scenario once it is ratified. Placement: the guard is part of the Beads substrate and its harness gates every janitor aggregate, so the clause sits beside the existing guard entry-point bullet in constraints.md.

### Proposed Changes

In SPECIFICATION/constraints.md, under '## Beads substrate constraints', immediately after the bullet that begins '`bd` is invoked through a managed public entry point', add:

- The lifecycle guard's test harness starts a throwaway loopback capture server for its telemetry cases. When starting it, the harness MUST wait until the server has written its port file, the server process has exited, or 30 seconds have elapsed, whichever comes first; it MUST NOT fail a telemetry case only because the server took longer than two seconds to write its port file. When the server has not written its port file by the end of that wait, the harness MUST fail the case with a line naming the capture server's exit status (or that it was still running at the bound) and its captured standard error, and MUST stop any capture server process it started.

In SPECIFICATION/scenarios.md, append a new scenario after the current last scenario, numbered as the next free scenario number at revise time:

## Scenario 259 — The lifecycle guard harness waits for a slow capture server and names a failed one

```gherkin
Feature: The lifecycle guard's test harness starts its telemetry capture server on a bounded, diagnosable wait

  Scenario: A capture server slower than two seconds does not fail a telemetry case
    Given the guard harness starts its telemetry capture server
    And the server writes its port file after more than two seconds and before 30 seconds
    When the harness runs a telemetry case against that server
    Then the harness MUST wait for the port file rather than failing the case
    And the case's outcome MUST reflect the guard's telemetry behaviour, not the start delay

  Scenario: A capture server that exits before writing its port file is named
    Given the guard harness starts its telemetry capture server
    And the server process exits before writing its port file
    When the harness's start wait ends
    Then the harness MUST end the wait when the process exits, without waiting for the 30-second bound
    And the failure line MUST name the server's exit status and its captured standard error

  Scenario: A capture server still silent at the bound is stopped and named
    Given the guard harness starts its telemetry capture server
    And the server has neither written its port file nor exited after 30 seconds
    When the harness's start wait ends
    Then the failure line MUST state that the server was still running at the bound and include its captured standard error
    And the harness MUST stop the capture server process it started
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the new scenario heading (test MAY be "TODO" with a reason naming bd-ib-qbwd7n).
