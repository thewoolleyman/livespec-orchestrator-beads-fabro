---
topic: dispatcher-fabro-rm-deletions-burst
author: claude-opus-5-5
created_at: 2026-11-03T09:03:13Z
---

## Proposal: Defer ended-run collection while a factory runs any run, and pace every Dispatcher run deletion per factory behind committed settings

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the collection clause of §"Dispatcher policy settings" → "Sandbox retention and collection". While the factory's run inventory shows a running run, a closed item's ended-run sandbox is deferred rather than deleted, and it is collected on the first pass at which the factory runs nothing. Every Dispatcher run deletion against a factory with a running run (ended-run collection, stall cancel, wall-budget cancel, stale-item reap) is paced host-wide by a minimum interval. Both are committed per-factory `dispatcher.factories.<name>` settings, defaulting to deferral on and 60 seconds, and turning deferral off with an interval of 0 restores today's unpaced deletion. Scenario 281's collection step is narrowed to match, and two scenarios are added to it.

### Motivation

Breakage, measured 2026-11-03 by fabro-currency and relayed by legacy-coordinator-agent. Petri's run store is a 102 GB SQLite database with a 5 s busy_timeout, and a `fabro rm -f` there takes up to 26.8 s (p50 1.0 s; outliers of 8-27 s). At 08:05Z and 08:09Z, Dispatcher delete bursts (4 deletes back to back, then 2) held the store locked for 8-21 s. Every concurrent run's append failed with "database is locked", and seven live runs were interrupted and resumed onto re-acquired sandboxes. The deleting clients are ended-run collection, stall cancel, the wall-budget watch and the stale-item reap. Ended-run collection runs unconditionally on every reconcile-runs pass, which several Dispatcher paths reach, and it deletes every collectable run back to back. No committed setting can defer or pace it, so no configuration-only mitigation exists. Pacing alone prevents the bursts, but one slow delete can still fail concurrent appends, so collection, which has no urgency, is deferred entirely while runs are active and done in the factory's drain-to-zero windows. Cancels and reaps act on live runs and still delete, under the pacing. fabro-currency's store-side fix (bd-ib-h7kbco: retry appends on SQLITE_BUSY, short delete transactions) ships only at main petri's zero-run restart. Once it ships, an operator can return to unpaced deletion through the committed settings with no code change. Implementation work item: bd-ib-vh23ja (P0, plan bd-ib-k7ymgx), held at the spec-change tier for this topic. The governing-heading judgement named §"Dispatcher policy settings" as the section to generalize, which contains the "Sandbox retention and collection" subsection.

### Proposed Changes

Two edits. Every other sentence of the edited subsection and scenario is unchanged.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher policy settings" → "Sandbox retention and collection".**

After the paragraph beginning "Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox through its provider's own delete operation", insert:

> **Deletion pacing on a busy factory.** A factory's run deletions contend with its live runs for the factory's run store, so a deletion burst can fail the record writes of every run the factory is executing. Two committed per-factory settings in `dispatcher.factories.<name>` therefore govern every run deletion the Dispatcher issues against that factory. The Dispatcher MUST read both on every pass, so a changed value takes effect without a restart:
>
> - `defer_collection_while_active` (boolean, default `true` when absent). While it is `true` and the factory's run inventory taken by the pass shows at least one running run, the pass MUST NOT delete any closed item's ended-run sandbox on that factory. It MUST journal each sandbox it defers, naming the run id and the factory, and MUST leave it collectable. On the first pass at which the factory's run inventory shows no running run, the Dispatcher MUST delete every deferred sandbox that is still collectable under the rule above. While it is `false`, and the minimum interval below is greater than 0, one pass that sees a running run on the factory MUST delete at most one ended-run sandbox there, leaving the rest for later passes.
> - `rm_min_interval_seconds` (non-negative number, default `60` when absent). While the factory's run inventory shows at least one running run, the Dispatcher MUST NOT start a run deletion against that factory until at least this many seconds have passed since the start of the previous run deletion against it by any Dispatcher process on the same host. This holds whichever caller issues the deletion: ended-run collection, a stall cancel, a whole-run wall-budget cancel, a stale-item reap, or a reconcile-runs termination. A deletion the interval defers MUST be journaled, naming the run id, the factory, the deleting caller and the earliest instant the next deletion may start. A cancel whose deletion is deferred MUST still stop the run from progressing at the moment of the cancel decision. Only the deletion of its record MAY wait.
>
> With `defer_collection_while_active` set to `false` and `rm_min_interval_seconds` set to `0`, the Dispatcher MUST delete exactly as it does without these settings. A deferral under either setting MUST NOT reopen, block or otherwise transition the run's work-item, and a deferred deletion remains subject to the retry and idempotence rules of this subsection.

In the same subsection, replace "Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox" with "Once the run's work-item is closed, the Dispatcher MUST delete that run's sandbox, subject to the deletion pacing below,".

**2. `SPECIFICATION/scenarios.md`, "## Scenario 281 — An ended run's Kubernetes sandbox survives while its item awaits a human and is deleted through its provider once the item closes".**

The H2 heading is unchanged, so `tests/heading-coverage.json` needs no edit. In the existing scenario, replace "When run A's work-item is closed and the Dispatcher's next pass runs" with "When run A's work-item is closed and the Dispatcher's next pass runs while no run on that factory is running". Then append two scenarios inside the same gherkin block:

```gherkin
  Scenario: Collection is deferred while the factory runs any run
    Given the factory's committed defer_collection_while_active setting is absent
    And an ended run C whose work-item is closed, on a factory that is running run D
    When the Dispatcher's next pass runs
    Then run C's sandbox still exists and the pass journals run C's collection as deferred
    When run D ends and the Dispatcher's next pass sees no running run on the factory
    Then run C's sandbox is deleted through the provider's delete operation

  Scenario: Deletions against a busy factory are paced host-wide
    Given the factory's committed rm_min_interval_seconds is 60 and the factory is running a run
    And one Dispatcher process started a run deletion against that factory 10 seconds ago
    When a second Dispatcher process on the same host decides to cancel a stalled run on that factory
    Then the stalled run stops progressing at once
    And the deletion of its record waits until 60 seconds after the first deletion started
    And the pass journals the deferred deletion with the run id, the factory, the caller and the earliest start instant
```

The scenarios MUST be exercised by the implementation work item's tests (bd-ib-vh23ja).
