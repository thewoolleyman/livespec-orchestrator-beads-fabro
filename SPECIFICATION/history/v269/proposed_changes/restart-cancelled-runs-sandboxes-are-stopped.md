---
topic: restart-cancelled-runs-sandboxes-are-stopped
author: claude-opus-5-5
created_at: 2026-11-01T21:15:47Z
---

## Proposal: A run that ended with its provider sandbox still running has that sandbox stopped through its provider

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Extend contracts.md §"Dispatcher policy settings" → "### Sandbox retention and collection" so that an ended run whose provider sandbox is still running, as when a fabro-server restart cancels in-flight runs, has that sandbox stopped through the provider's own stop operation on the Dispatcher's next pass. The pod is gone and its namespace quota is released, while the driver record and node workspace stay subject to the existing retention and collection rules. Add Scenario 292 exercising it, with a heading-coverage TODO entry owned by bd-ib-lupvil.

### Motivation

Measured 2026-10-24 on the gmktec production factory (:32276): one fabro-server restart cancelled runs 01M5NTVGNJHN and 01M5NV05ADES, which went `failed` at 0 ms, yet their pods kept running in namespace `factory` for six hours and held 8 of the `factory-runs` quota's 24 cpu. Run 01M5PFE3YW00 was then refused at sandbox acquire with a 403 quota error while only four runs were live. Recovery took a by-hand driver delete. At a normal run end Petri calls the provider's stop. A run cancelled by a server restart never reaches that call, so nothing stops its pod. Work-item bd-ib-lupvil carries the fix, but no ratified heading governs restart-time sandbox cleanup: its reference names the credential section, and the R316 Definition-of-Done check refused it on 2026-10-24. The clause says STOP, not delete, on purpose. Deleting would also remove the node workspace, which the existing retention rule keeps while the run's item rests at `blocked` or `needs-human`. Placing it in the existing subsection keeps one pass responsible for every ended run's provider sandbox.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, subsection `### Sandbox retention and collection` (under `## Dispatcher policy settings`), insert this paragraph after the paragraph that begins "Once the run's work-item is closed":

> An ended run whose sandbox is still running, for instance because a Fabro server restart cancelled the run before its own end-of-run stop, MUST have that sandbox stopped through its provider's own stop operation by the Dispatcher's next pass, whatever its work-item's status, so that the sandbox's compute is released and the namespace quota it held counts only live runs. Stopping MUST NOT remove the driver record or the node workspace directory; those remain subject to the retention and collection rules above. A stop the provider refuses or cannot complete MUST be journaled with the run id and the provider's reason, and MUST be retried on a later pass. A pass finding an ended run's sandbox already stopped MUST record nothing further for it.

In the same subsection, replace the sentence "A run whose work-item is at any other status keeps today's behaviour; this subsection neither retains nor collects its sandbox." with "A run whose work-item is at any other status keeps today's behaviour; this subsection neither retains nor collects its sandbox, although the stop rule above still applies to it.", so that it does not contradict the new paragraph's "whatever its work-item's status".

Then replace the subsection's closing line "Scenario 281 in `scenarios.md` exercises this subsection." with "Scenarios 281 and 292 in `scenarios.md` exercise this subsection."

2. In `SPECIFICATION/scenarios.md`, append after Scenario 291:

```
## Scenario 292 — A run a server restart cancelled has its still-running Kubernetes sandbox stopped through its provider

```gherkin
Feature: Sandbox retention and collection

  Scenario: A restart-cancelled run's pod is stopped, its workspace retained
    Given a factory run on the Kubernetes provider whose sandbox pod is running
    And the Fabro server restarts and records that run as ended without stopping its sandbox
    When the Dispatcher's next pass runs
    Then the run's sandbox is stopped through the provider's stop operation and its pod no longer exists in its namespace
    And the namespace quota's used cpu equals the cpu of the live runs' pods
    And the run's driver record and node workspace directory still exist
    When a further pass runs
    Then nothing further is recorded for that run and the pass does not fail
```
```

3. In `tests/heading-coverage.json`, add one entry: heading "## Scenario 292 — A run a server restart cancelled has its still-running Kubernetes sandbox stopped through its provider", spec_root "SPECIFICATION", spec_file "scenarios.md", test "TODO", work_item "bd-ib-lupvil", reason "An integration-tier test is owed for this heading: ratified with proposal restart-cancelled-runs-sandboxes-are-stopped, and the owning work-item bd-ib-lupvil stops a restart-cancelled run's still-running Kubernetes sandbox through its provider, together with the test that binds this entry."
