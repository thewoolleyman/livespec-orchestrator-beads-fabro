---
topic: stale-fabro-assignee-reconciliation
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T10:14:15Z
---

## Proposal: A ready item still assigned fabro is a stale assignee that reconciliation clears or holds

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen contracts.md §"Stranded claim release" so every reconciliation surface also surveys a ready item whose assignee is still fabro. Such an item is a stale assignee, not a dispatch claim: no terminal disposition is owed. On the owning host, with no live owner and a terminal-failed or absent run, the Dispatcher clears only the fabro assignee, with a stale-assignee-clear journal record and ledger comment under the existing recovery-exclusivity rules; every other case is held with a named reason, including run-succeeded naming reconcile-merged. New Scenario 210 exercises it.

### Motivation

Measured 2026-10-20 ~09:50Z on this tenant (registered build v0.226.1): reconcile-runs --dry-run --json listed only bd-ib-davaxq and bd-ib-7f66ar in held and nothing in reconciled, while four items read ready with assignee fabro and a terminal last run: bd-ib-z2y4ca (run 01M4FWX1Z9J7 failed 2026-10-09), bd-ib-t4dtx4 (01M4VSTCF4GW failed, PR 2913 closed unmerged), bd-ib-ukht2p (01M4W2BX1K4F failed at 34 s, needs-human cause recorded) and bd-ib-ma3fvj (01M58N2ATX8N SUCCEEDED, PR 3271 open). The ratified section defines a dispatch claim as an active fabro item and surveys only those, so these items appear in neither list and their stale assignee survives indefinitely; the coordinator's R289 ownership sweep read all four as ready and seatless, and a fill nearly dispatched ma3fvj fresh on top of its open PR. Filed as bd-ib-3lbt4o by plan session petri-factory-on-gmktec; its dod-preflight correctly refused it because no ratified heading governs the shape. Coordinator routing R293 (gitops-fleet-capacity-monitoring) assigned this proposal to plan session spec-implementation-lockstep.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Stranded claim release":

1. In the **Survey** bullet, extend the first sentence so every reconciliation surface also surveys "every stale assignee as "Stale assignee clearance" below defines one".

2. Insert a new bullet, **Stale assignee clearance**, after "Terminal-run completion" and before "Holds". It defines a *stale assignee* as a work-item resting at `ready` whose assignee is still `fabro`, and states that it is not a dispatch claim: its claim ended when the item left `active`, so no terminal disposition is owed and reconciliation MUST NOT apply one. The `rework:pending` / `merge-hold:` survey exclusion applies, and the Attribution, Run state and Owner liveness measurements are taken. When the item is attributed to this host, its stamped run is terminal and did not succeed or the factory positively reports it absent, and no live owner is established, the Dispatcher MUST clear the `fabro` assignee, leaving status, labels and run stamp unchanged; journal one `stale-assignee-clear` record naming the item, run id, factory and run state (`failed` or `absent`); and write one ledger comment naming the same facts. The clearance follows "Recovery is exclusive on its host and convergent", with the assignee write in place of the status transition and the re-reads requiring the item still `ready`, assigned `fabro` and stamped with the same run. Every stale assignee not cleared is left exactly as it is and listed in `held` with the first applicable reason among `claim-unattributable`, `attribution-pending`, `owner-elsewhere`, `factory-unobservable`, `run-live`, `liveness-unobservable`, `dispatch-live`, `run-succeeded`, `claim-changed` and `effect-unobservable`, in that order; a `run-succeeded` hold names `reconcile-merged` as its recovery.

3. In the **Status changes** bullet, add: "A stale assignee clearance changes no status."

4. Change the closing sentence to "Scenarios 196 and 210 in `scenarios.md` exercise this section."

In `SPECIFICATION/scenarios.md`, append `## Scenario 210 — Reconciliation clears a stale fabro assignee from a ready item, and holds with a named reason every one it cannot clear`, with a Background of a ready item assigned fabro stamped by this host, and scenarios for: a failed run cleared with no terminal disposition; an absent run cleared; a hold outline over the ten reasons; a succeeded run held as run-succeeded naming reconcile-merged; and a replay that writes nothing.

The revise pass that accepts this proposal MUST add the Scenario 210 entry to `tests/heading-coverage.json` (test `TODO`, owned by bd-ib-3lbt4o) and a matching `tests/heading-coverage-debt.json` row in the same change.
