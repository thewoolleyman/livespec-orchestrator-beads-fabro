---
topic: ended-runs-kubernetes-sandboxes-are
author: claude-opus-5-5
created_at: 2026-10-31T18:01:07Z
---

## Proposal: An ended run's Kubernetes sandbox is retained while its item awaits a human and deleted through its provider once the item closes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `### Sandbox retention and collection` subsection to contracts.md `## Dispatcher policy settings`. It states when an ended run's Kubernetes sandbox is kept: while its work-item rests at `blocked` or `needs-human`. It also states when the sandbox is deleted through its provider: once the item closes, so its driver record and its node workspace directory are gone. One scenario covers both halves.

### Motivation

Work item bd-ib-u5facl, under plan kubernetes-sandbox-backend (epic bd-ib-nmuyjc), carries a coordinator ruling (livespec-dev-tooling-dfixhe, 2026-10-24): keep a run's workspace while its work-item is blocked or needs-human, and collect it once the item closes. Today nothing collects it, so every ended run leaks a driver record and a node workspace directory without bound. The driver's own `delete` already clears the pod, the workspace and the record, so only a caller of it after retention is missing. The dispatch-time Definition-of-Done preflight (2026-10-31T17:53:44Z) found the retention behaviour stated nowhere in the ratified spec (governing-heading-kind: unstated) and named `## Dispatcher policy settings` as the clause to generalize.

### Proposed Changes

Add the following subsection to SPECIFICATION/contracts.md under `## Dispatcher policy settings`, immediately after `### Sandbox image enumeration`:

### Sandbox retention and collection

This subsection governs the sandbox of a factory run that has ENDED and whose sandbox is provided by a registered sandbox provider, such as the Kubernetes provider. A run's sandbox is its provider-held driver record together with the node workspace directory that provider allocated for the run.

While the run's work-item rests at `blocked` or `needs-human`, the Dispatcher MUST NOT delete, and MUST NOT cause the deletion of, that run's sandbox, because a human resolving the item may need the run's workspace. Retention MUST NOT depend on how long the item has rested there.

Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox through its provider's own delete operation, so that the driver record and the node workspace directory are both gone. The Dispatcher MUST NOT remove either one by any route other than that provider operation, because a workspace removed behind the provider leaves a driver record naming a directory that no longer exists. A deletion the provider refuses or cannot complete MUST be journaled with the run id and the provider's reason, and MUST be retried on a later pass; it MUST NOT reopen, block or otherwise transition the closed item.

A run whose work-item is at any other status keeps today's behaviour; this subsection neither retains nor collects its sandbox.

Collection MUST be idempotent: a later pass finding a closed item's sandbox already gone MUST record nothing further for it and MUST NOT fail.

Add one scenario to SPECIFICATION/scenarios.md, numbered with the next free scenario number at revise time, and link it in tests/heading-coverage.json in the same revise:

## Scenario NNN — An ended run's Kubernetes sandbox survives while its item awaits a human and is deleted through its provider once the item closes

Given two ended factory runs on the Kubernetes provider, run A whose work-item rests at `needs-human` and run B whose work-item rests at `blocked`
When the Dispatcher's next pass runs
Then run A's and run B's driver records and node workspace directories still exist
When run A's work-item is closed and the Dispatcher's next pass runs
Then run A's sandbox is deleted through the provider's delete operation, and its driver record and node workspace directory no longer exist
And run B's driver record and node workspace directory still exist
When a further pass runs
Then nothing further is recorded for run A and the pass does not fail.
