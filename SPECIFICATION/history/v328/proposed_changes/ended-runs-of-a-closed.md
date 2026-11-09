---
topic: ended-runs-of-a-closed
author: claude-opus-5-5 (kubernetes-sandbox-backend plan session)
created_at: 2026-11-08T20:41:32Z
---

## Proposal: Ended runs of a closed item are collected whichever repository dispatched them

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md §"Sandbox retention and collection" requires a closed item's ended-run sandbox to be deleted through its provider, but it never says WHICH repository's pass performs the deletion. In practice only the repository whose host timer runs reconcile-runs collects its own runs, and every other dispatching repository collects only inside its own dispatch or resume reconcile, so a closed item's sandbox is collected only if its own repository happens to dispatch again. This proposal makes collection fleet-wide: one periodic pass collects every dispatching repository's closed items' ended runs. It leaves in place any run whose item cannot be resolved, and journals each collection and refusal with the dispatching repository. It adds a Scenario 281 scenario exercising the new paragraph.

### Motivation

Work-item bd-ib-q4xgcp, filed on coordinator ruling R493 (plan bd-ib-nmuyjc, 2026-11-08). The host measurement on 2026-11-08 at about 20:30Z is the bd-ib-u5facl host-leg comment. The only periodic collector, /etc/systemd/system/reconcile-runs.timer, runs `dispatcher.py reconcile-runs --repo /data/projects/livespec-orchestrator-beads-fabro`, so it collects only runs that repository's journal attributes: 1704 ended-run-collected records. Other repositories collect only during their own reconcile: livespec-dev-tooling 521, livespec-overseer 98, and livespec-console-beads-fabro 0. 55 non-empty workspaces of CLOSED items, about 48 GB under /srv/factory-workspaces on gmktec-xubuntu (76% full) and poweredge-xubuntu, were never collected. The coordinator ruled for FLEET SCOPE (every repository that dispatches to the factory) and for ONE fleet-wide periodic pass rather than per-repository timers. Scenario 281's steps state retention and collection but not which pass reaches another repository's runs, so the spec-change-tier check rested bd-ib-q4xgcp at spec-change, linked to this topic.

### Proposed Changes

In SPECIFICATION/contracts.md §"Sandbox retention and collection", insert the following paragraph immediately after the paragraph that begins "Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox":

> **Collection reaches every dispatching repository's runs.** The collection duty above binds whichever repository dispatched the run. The Dispatcher's periodic pass on a dispatching host MUST collect, on each factory it surveys, every ended run whose work-item is closed in the ledger of the repository that dispatched that run, for every repository whose runs that factory carries, and not only the runs that the pass's own repository dispatched. One periodic pass per dispatching host MUST suffice for every dispatching repository's runs to be collected; a repository's runs MUST NOT depend on a periodic pass of that repository's own. The pass MUST resolve each run's work-item through the run's own recorded work-item identity and the dispatching repository's own ledger. A run whose work-item cannot be resolved in any dispatching repository's ledger, or whose ledger cannot be read on that pass, MUST be left in place with its server run record and sandbox, and MUST NOT be treated as closed. A run that maps to no work-item, including the factory's clearance and availability-probe runs, MUST be left in place as before. Each collection and each refusal the pass makes MUST be journaled naming the run id, the dispatching repository, the work-item id and the item status the pass read. The deletion pacing, deferral, retry and idempotence rules of this subsection apply unchanged to every run this paragraph collects. Scenario 281 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, under the existing H2 heading `## Scenario 281 — An ended run's Kubernetes sandbox survives while its item awaits a human and is deleted through its provider once the item closes`, append the following scenario to the end of that heading's `Feature: Sandbox retention and collection` Gherkin block, after the scenario "Deletions against a busy factory are paced host-wide". The H2 heading text MUST NOT change, so tests/heading-coverage.json needs no co-edit:

```gherkin
  Scenario: One periodic pass collects a closed item's runs whichever repository dispatched them
    Given repository P, whose host timer starts the Dispatcher's periodic pass, and repository Q both dispatch to one factory
    And an ended run E that repository Q dispatched, whose work-item is closed in repository Q's ledger
    And an ended run F that repository Q dispatched, whose work-item rests at `blocked` in repository Q's ledger
    And an ended run G whose work-item cannot be resolved in any dispatching repository's ledger
    When the periodic pass started by repository P's timer runs while no run on that factory is running
    Then run E's sandbox is deleted through the provider's delete operation
    And run F's and run G's server run records and sandboxes still exist
    And the pass journals run E's collection and run G's refusal, each naming the run id, the dispatching repository, the work-item id and the item status it read
```
