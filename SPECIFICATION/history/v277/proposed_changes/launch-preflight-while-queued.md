---
topic: launch-preflight-while-queued
author: claude-opus-5-5
created_at: 2026-11-02T16:41:35Z
---

## Proposal: A queued provisional launcher runs its launch-time preflight while it waits, reuses a fresh pass at the FIFO head, and keeps FIFO bind order

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md "## Provisional fleet launch scripts" so a fleet-launch/ launcher runs its launch-time Definition-of-Done preflight while it is queued behind older FIFO tickets, not only after it reaches the head. A pass is reusable for FLEET_LAUNCH_PREFLIGHT_REUSE_S. A launcher reaching the head with a reusable pass goes straight to the mutex, and one with a stale or absent pass re-takes the preflight there. A failed preflight ends the launcher, which drops its ticket without taking the mutex. FIFO bind order is unchanged and no second ordering rule is added. The mutex covers only the binding count up to its release, which comes before drive impl starts. The check-fleet-launch harness's required cases grow by four. New Scenario 297 states the behaviour.

### Motivation

Work-item bd-ib-x7bwug, routed by legacy-coordinator-agent under R301 (2026-11-02) from livespec-dev-tooling plan gmktec-factory-placement, whose fleet-cap item livespec-dev-tooling-mmglfv reads gmktec throughput. legacy-dispatcher-agent measured each launch spending 3-5 minutes in the one-at-a-time section, which allows about 15 launches per 45 minutes, while the fleet ran 4-9 live against a cap of 10 and gmktec read 74-96% idle. Reading the committed fleet-launch/dispatch-dual.sh and the seat's running copy locates the cause. The main loop's FIFO-head check sends every launcher but the one holding the oldest live ticket back to sleep, and that check comes BEFORE launch_preflight, the model-backed dod-preflight. The mutex is already released right after the binding count. So every launch's preflight runs one at a time at the head of the FIFO, and that section, not the mutex, is what serializes launches. The filing-time spec-change-tier judgement on bd-ib-x7bwug found that this section states FIFO order and the mutex but not a queued-time preflight or its reuse window, so the behaviour is ratified here before the item is admitted. The reuse window keeps the intent of the seats' rule that the preflight is re-taken at launch, because a pass older than the window is re-taken at the head. FIFO order is explicitly preserved and no second ordering rule is introduced, so the plan radar-and-deterministic-admission, whose dispatcher cutover will later own launch order, replaces the same FIFO interface it would have replaced before. In-flight survey: no open pull request touches SPECIFICATION/. The remote spec/fleet-launch-factory-class-pressure-gate branches are already ratified on master as this section's factory-class pressure paragraph and Scenario 296, and this proposal aligns with them.

### Proposed Changes

### contracts.md — "## Provisional fleet launch scripts"

Insert the following paragraph immediately after the paragraph that begins "The threshold MUST be assigned in `fleet-launch/config.sh`" and before the paragraph that begins "`just check` MUST run a `check-fleet-launch` target":

A `fleet-launch/` launcher that holds a per-factory FIFO ticket MUST run its launch-time Definition-of-Done preflight while it is queued behind older tickets, and MUST NOT wait to reach the head of the FIFO before its preflight starts. A preflight pass is reusable for `FLEET_LAUNCH_PREFLIGHT_REUSE_S` seconds, a host value assigned in `fleet-launch/config.sh` and overridable like any other. A launcher that reaches the head of the FIFO holding a reusable pass MUST proceed to that factory's mutex without running the preflight again. A launcher that reaches the head with no pass, or with only a pass older than the reuse window, MUST run the preflight again before it takes the mutex. A failed preflight, whether it ran while queued or at the head, MUST end that launcher without a launch, and the launcher MUST drop its FIFO ticket without taking the mutex. Running the preflight while queued MUST NOT change the order in which queued launchers bind: tickets still bind in FIFO order, and a launcher MUST NOT add any ordering rule beside the FIFO ticket. The per-factory mutex MUST be held only from the binding count to its release, and that release MUST come before `drive --action impl:<item>` starts.

In the `check-fleet-launch` paragraph, replace "holding a launch when factory-class pressure is above the threshold; and holding a launch when the node reading cannot be taken or parsed." with "holding a launch when factory-class pressure is above the threshold; holding a launch when the node reading cannot be taken or parsed; starting a queued launcher's preflight before an older ticket binds while the older still binds first; reusing a preflight pass younger than `FLEET_LAUNCH_PREFLIGHT_REUSE_S` at the head of the FIFO; re-running a stale preflight pass at the head before the mutex; and dropping the FIFO ticket of a launcher whose preflight fails while it is queued, without taking the mutex."

### scenarios.md — new scenario after "## Scenario 296 — The provisional launcher's shared-node gate holds on factory-class pressure, not whole-host idle"

Use the next free scenario number at revise time (297 as of spec v276):

## Scenario 297 — A queued provisional launcher runs its preflight while it waits and still binds in FIFO order

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: a launcher queued on a factory's FIFO spends its wait on its own preflight
  Scenario: two queued launchers preflight concurrently
    Given fleet-launch/config.sh values overridden to stub factory boards, a stub preflight that records its start time, and throwaway queue, lock, in-flight and state directories
    And two launchers hold FIFO tickets for the same factory, the older ahead of the younger
    When both launchers poll while the older holds the head of the FIFO
    Then the younger launcher's preflight starts before the older launcher binds
    And the older launcher binds before the younger launcher

  Scenario: a fresh pass is reused at the head of the FIFO
    Given a queued launcher whose preflight passed less than FLEET_LAUNCH_PREFLIGHT_REUSE_S seconds ago
    When it reaches the head of the FIFO and the factory is green
    Then it takes the factory's mutex without running the preflight again

  Scenario: a stale pass is re-taken at the head of the FIFO
    Given a queued launcher whose only preflight pass is older than FLEET_LAUNCH_PREFLIGHT_REUSE_S seconds
    When it reaches the head of the FIFO
    Then it runs the preflight again before it takes the factory's mutex

  Scenario: a preflight that fails while queued drops the ticket
    Given a queued launcher whose stub preflight fails
    When the preflight returns
    Then the launcher exits without a launch
    And its FIFO ticket is gone from the queue directory
    And it never created the factory's mutex
```

### tests/heading-coverage.json — co-edit at revise time

Add an entry for the new Scenario 297 heading, verbatim. Until bd-ib-x7bwug lands the harness cases, the entry is a TODO naming that owed hermetic-harness test and bd-ib-x7bwug as its owner, in the form this repository's heading-coverage gate requires. No existing H2 heading is renamed or removed.
