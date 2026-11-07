---
topic: an-ended-run-s-kubernetes
author: claude-opus-5-5
created_at: 2026-11-07T20:32:24Z
---

## Proposal: An ended run's sandbox is collected once its item returned to ready or backlog with its work on origin

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Dispatcher's sandbox collection today reaches only runs whose work-item closed. This extends it to an ended run whose item returned to ready or backlog, once every commit that run produced is reachable from a ref on origin, and keeps and journals the sandbox otherwise. Retention at blocked and needs-human is unchanged.

### Motivation

Work item bd-ib-jshkjz, under plan bd-ib-nmuyjc. Measured 2026-11-03: pod petri-01m6dnpwsxfrd4b38rqyhptb9k-l0 held a 4-CPU Guaranteed reservation on hp-xubuntu after its run 01M6DNPWSXFR for bd-ib-ch44wn ended cancelled on 2026-11-02T09:50Z with its work already on origin. bd-ib-ch44wn had returned to ready, so collection, which deletes only runs whose item is closed, never reached it, and it was reclaimed by hand. The behaviour changes what Scenario 281 and the clause state, so it needs a ratified proposal before the item can be dispatched; the item's spec-change hold on topic an-ended-run-s-kubernetes refused every launch while none existed (spec-implementation-lockstep, 2026-11-07).

### Proposed Changes

In SPECIFICATION/contracts.md §"Sandbox retention and collection", immediately after the paragraph beginning "Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox", add this paragraph:

An ended run whose work-item has returned to `ready` or `backlog` MUST also be collected, by the same provider delete operation and subject to the same deletion pacing, retry and idempotence rules, once every commit that run produced is reachable from a ref on the run's origin. While any commit that run produced is not reachable from a ref on origin, the Dispatcher MUST keep that run's sandbox and MUST journal it as retained for unpublished work, naming the run id, because the sandbox then holds the only copy of that work. A read of origin that cannot be completed MUST count as not reachable. This collection MUST NOT apply to a clearance run, an availability-probe run or a run with no work-item, and it MUST NOT reopen, block or otherwise transition the item.

In the same subsection, replace the sentence "A run whose work-item is at any other status keeps today's behaviour; this subsection neither retains nor collects its sandbox, although the stop rule above still applies to it." with:

A run whose work-item is at any status this subsection does not name keeps today's behaviour; this subsection neither retains nor collects its sandbox, although the stop rule above still applies to it.

In the same subsection, replace "Collection MUST be idempotent: a later pass finding a closed item's sandbox already gone" with "Collection MUST be idempotent: a later pass finding a collectable sandbox already gone". In the `defer_collection_while_active` bullet, replace "any closed item's ended-run sandbox" with "any collectable ended-run sandbox".

In SPECIFICATION/scenarios.md, retitle `## Scenario 281 — An ended run's Kubernetes sandbox survives while its item awaits a human and is deleted through its provider once the item closes` to `## Scenario 281 — An ended run's Kubernetes sandbox survives while its item awaits a human and is deleted through its provider once the item closes or returns to ready with its work on origin`, update that heading's row in tests/heading-coverage.json in the same change, and add this scenario to its Gherkin feature after `Scenario: Retained while awaiting a human, collected through the provider once closed`:

  Scenario: Collected once its item returned to ready and its work is on origin
    Given two ended factory runs on the Kubernetes provider while no run on that factory is running, run E whose work-item rests at `ready` with every commit it produced reachable from a ref on origin, and run F whose work-item rests at `backlog` with a commit reachable from no ref on origin
    When the Dispatcher's next pass runs
    Then run E's sandbox is deleted through the provider's delete operation, and its driver record and node workspace directory no longer exist
    And run F's driver record and node workspace directory still exist
    And the pass journals run F as retained for unpublished work, naming its run id
    And neither work-item's status changes

