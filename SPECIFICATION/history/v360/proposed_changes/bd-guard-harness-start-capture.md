---
topic: bd-guard-harness-start-capture
author: claude-opus-5-5
created_at: 2026-11-12T05:09:14Z
---

## Proposal: The lifecycle guard harness bounds every wait on its capture server and names a server it cannot stop

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the lifecycle guard test-harness bullet of the Beads substrate constraints, and Scenario 269, so that a failed liveness probe on a capture server that is still running is not read as an exit, stopping the capture server returns within a fixed 10-second bound, and a capture server still running after its stop fails the telemetry case with a line naming it. Today the start wait is bounded only while the probe succeeds, and the stop wait is unbounded, so a refused signal leaves the harness waiting forever and its gate with no verdict.

### Motivation

Measured in livespec-dev-tooling-ddy5xu (root-cause comment, 2026-11-12 ~04:55Z). On gamingpc-xubuntu (kernel 7.0.0-43, AppArmor parser 5.0.2), AppArmor denies signal sends between processes inside a gate container (profile cri-containerd.apparmor.d, peer cri-containerd.apparmor.d//&unconfined).

The harness in `bd-guard/test/run-tests.sh` read that denial as an exit:
- `start_capture` (around line 213) runs `if ! kill -0 "$CAP_PID"; then wait "$CAP_PID"`, and has the same pattern around line 228 after the bound.
- `kill -0` failed with a permission error while capture.py was alive. The harness read that as an exit and called an unbounded `wait` on a live server.
- On gamingpc's /proc, run-tests.sh sat in do_wait/kernel_wait4 with wait4(-1); its only child, capture.py, was alive with ShdPnd 0 and SigBlk 0.
- `stop_capture` (around line 237) runs `kill "$CAP_PID"; wait "$CAP_PID"`, which has no bound either.
- So check-bd-guard held its gate Job open until the gate client's 3600 s bound, three runs out of three (gate Jobs 5mxn4 and 9p9pc, and repro Job 5g7z6).

The node configuration is being fixed separately by its owner. This proposal makes the harness end with a red verdict instead of hanging, whatever the signal environment.

Scenario 269 and the "Beads substrate constraints" bullet already state the bounded start wait. They do not state that a failed probe is not an exit, that the stop is bounded, or that a server which cannot be stopped is named as a failed case. Root-fix work item bd-ib-w4bbbd is held at the spec-change tier for this topic, on legacy-coordinator-agent's ruling. Filed by the gate-job-resources seat (livespec-dev-tooling plan gate-job-resources).

### Proposed Changes

Two edits, plus a heading-coverage note. Every other sentence of the edited bullet, and every existing case of the scenario, stays unchanged.

**1. `SPECIFICATION/constraints.md`, §"Beads substrate constraints", the lifecycle guard test-harness bullet ("The lifecycle guard's test harness starts a throwaway loopback capture server ...").**

Replace the bullet with:

> - The lifecycle guard's test harness starts a throwaway loopback capture server for its telemetry cases. When starting it, the harness MUST wait until the server has written its port file, the server process has exited, or 30 seconds have elapsed, whichever comes first; it MUST NOT fail a telemetry case only because the server took longer than two seconds to write its port file. The harness MUST treat the server process as exited only on evidence that it has exited. A liveness probe that fails while the process may still be alive — for example `kill -0` refused with a permission error — MUST NOT be read as an exit, and the start wait MUST keep its 30-second bound. When the server has not written its port file by the end of that wait, the harness MUST fail the case with a line naming the capture server's exit status (or that it was still running at the bound) and its captured standard error, and MUST stop any capture server process it started. Every wait the harness performs on the capture server process MUST be bounded. Stopping the server MUST end its wait at a stop bound of 10 seconds after the stop signal is sent, and the harness MUST NOT wait on the process after that bound. Like the 30-second start bound, the stop bound is observed through the diagnostic the harness emits when it is reached, not by timing the harness. When the server is still running at the end of the stop wait, the harness MUST fail the telemetry case that started it with a line naming the capture server as still running after its stop, so that the harness run ends with a failing verdict rather than never ending.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 269 — The lifecycle guard harness waits for a slow capture server and names a failed one`.**

The heading text MUST stay unchanged. Append these three scenarios at the end of the existing gherkin fence:

```gherkin
  Scenario: A failed liveness probe on a capture server that is still running is not read as an exit
    Given the guard harness starts its telemetry capture server
    And the server process is still running and has not written its port file
    And the harness's liveness probe of the server process fails although the process has not exited
    When the harness's start wait continues
    Then the harness MUST NOT treat the server as exited
    And the harness MUST NOT wait on the server process without a bound
    And the start wait MUST end when the port file is written, the process is observed to have exited, or the 30-second bound elapses, whichever comes first

  Scenario: Stopping a capture server that does not exit returns within its bound
    Given the guard harness has started its telemetry capture server
    And the server process does not exit when the harness sends it the stop signal
    When the harness stops the capture server
    Then the stop MUST end its wait at the harness's stop bound, not at the server process's exit
    And the harness MUST NOT wait on the server process after that bound
    And the harness MUST record that the server was still running at the stop bound

  Scenario: A capture server that cannot be stopped is named as a failed case
    Given the guard harness has started its telemetry capture server
    And the server process is still running at the end of the harness's stop wait
    When the harness reports the telemetry case that started the server
    Then the case MUST be reported as failed
    And the failure line MUST name the capture server as still running after its stop
    And the harness run MUST end with a failing verdict rather than waiting for the server
```

**Heading-coverage co-edit note.** No `## ` heading is added, renamed or removed, so the revise commit MUST NOT add or drop a `tests/heading-coverage.json` row. The `## Scenario 269 — ...` row stays bound to its existing integration-tier test (`tests.integration.test_bd_guard_capture_start_scenario269.test_scenario269_binds_the_declared_check_to_capture_start_observations`). That test does not yet exercise the three appended cases. bd-ib-w4bbbd owns extending it, and the shell regression it binds (`bd-guard/test/run-tests.sh`), to the three new cases. The revise SHOULD record that ownership in the row's `reason` and set the row's `work_item` to bd-ib-w4bbbd until that item closes.
