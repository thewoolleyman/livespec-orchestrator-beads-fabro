---
topic: a-live-run-whose-dispatcher
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-11T23:47:31Z
---

## Proposal: Reconciliation applies the whole-run wall budget to a live run no dispatch still owns

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today a dispatch's own watch is the only thing that applies the whole-run wall budget. When the watch's re-attach supervision gives up on a run it cannot read, the dispatcher exits with the claim retained, and reconciliation then holds the still-running run as `run-live` on every pass, so nothing ever cancels it. This proposal adds a reconciliation duty, "Live-run wall budget". For a claim attributed to this host whose run is non-terminal and whose ownership lock no live process holds, reconciliation applies the watchdog's whole-run wall budget, its progress grading, its hard ceiling, its export-then-terminate disposition and its held arm, exactly as the run's own watch would. The host's periodic pass applies it to every dispatching repository it already reaches for collection. A dispatch that stops observing its run says on its outcome record that the budget is left to reconciliation. Hold reason `run-live` is narrowed accordingly, and Scenario 349 exercises the duty.

### Motivation

Owning work item bd-ib-ag633q, "A live run whose dispatcher gave up re-attaching is never wall-cancelled, because reconciliation holds it run-live without asking whether any dispatch still owns it". legacy-coordinator-agent (session 0f6da4ba) routed it to plan dispatcher-run-watch-cost (epic bd-ib-k7ymgx) on 2026-11-11. Measured on vmi3006760 that night: two of nine gmktec board runs held slots past their 21,600 s budget with no watcher. The first was bd-ib-p6ammc, run 01M75SD00Z90, at 370 min. Its dispatch journaled `fabro-reattach` at 19:53Z and 19:58Z, then at 20:00:27Z the outcome "run ... is possibly still alive; re-attach observation budget exhausted; work-item claim retained". From 20:33Z every timer:reconcile-runs pass journaled `stranded-claim-hold` reason `run-live` and cancelled nothing. The second was livespec-dev-tooling-symfx2, run 01M760HYV9CE, started by a direct `dispatcher.py dispatch`, which ended with the identical outcome. Re-attach supervision gives up after 12 unanswered `fabro inspect` reads, or after 600 s with no confirmed live read; the host was saturated (CPU pressure about 80%) from 19:40Z to 20:50Z. That give-up is shared by every dispatch entry point (fleet launcher `drive`, direct `dispatch`, `loop`), so the bound belongs to reconciliation and not to any one entry point. bd-ib-pxp2ve (PR #4966) already made re-attach supervision apply the budget WHILE it keeps observing. This proposal covers the run after supervision has stopped observing. The fleet-scope clause answers the coordinator's order that every repository able to create a petri run is covered. In-flight survey: no open proposal or spec branch touches the reconciliation clause or the wall-budget section; the open spec PRs #4977 and #4971 touch unrelated proposals, and reconcile-runs-prints-a-bare (this plan's own, on branch spec/reconcile-runs-prints-a-bare) amends a different hold reason (`attribution-pending`) in the same list and is compatible.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings", in the reconciliation clause: insert this new bullet IMMEDIATELY AFTER the bullet that begins "- **Terminal-run completion.**" (including its nested sub-bullets and its closing paragraph that ends "It MUST NOT be released and MUST NOT be converted into a needs-human decision."), and BEFORE the bullet that begins "- **Stale assignee clearance.**":

- **Live-run wall budget.** A dispatch's own watch is not the only bound on how long a run holds a factory slot. When the claim is attributed to this host, the factory reports its run non-terminal, every ownership lock location for the item on this host was read, and none is held by a live process, the Dispatcher MUST apply to that run §"Dispatcher progress watchdog" → "The whole-run wall budget" and the paragraphs that follow it ("Progress past the budget", "The hard ceiling", the budget disposition with its export-then-terminate precondition and its `run-wall-budget-exceeded` record, the `blocked` / `needs-human` rest, and the `run-wall-budget-held` arm with its verified-preservation-ref release and its escalation), exactly as the run's own watch would at a poll. The reconciliation pass stands in for the watchdog poll. The slot-holding clock MUST start at the instant the run's own record reports it first `running`. When the record carries no such instant, the budget is unmeasured, and the pass MUST NOT cancel on it, because no reconciliation pass observed the run's first `running` poll. A run within its budget, a run past its budget that is progressing, and a run whose budget is unmeasured are held as `run-live`. A run the pass cancels is listed in the pass's output with its `run-wall-budget-exceeded` record, and a held export is listed as `run-live`, naming its `run-wall-budget-held` record. The periodic pass on a dispatching host MUST apply this bullet to the claims of every dispatching repository it reaches under "Collection reaches every dispatching repository's runs", reading each claim, its ownership lock locations and its item in the repository that dispatched it. A claim whose repository's ledger or lock locations cannot be read on that pass MUST be held with the reason the hold list assigns, and MUST NOT be cancelled.

  When a dispatch's re-attach supervision stops observing a run it can no longer read, and the dispatch ends with its claim retained, the dispatch's outcome record MUST name the run and the factory, and MUST state that the run's whole-run wall budget is left to reconciliation under this bullet.

2. contracts.md, same clause, in the **Holds** list, item 5: "5. `run-live`: the run is non-terminal." MUST become "5. `run-live`: the run is non-terminal, and the bullet \"Live-run wall budget\" above does not take the budget disposition for it." No other hold reason changes, and the hold order is unchanged.

3. scenarios.md: append this new H2 section after the last ratified scenario:

## Scenario 349 — Reconciliation applies the whole-run wall budget to a live run no dispatch still owns

```gherkin
Feature: The whole-run wall budget outlives the dispatch that watched the run
  As a maintainer whose factory slots are finite
  I want a run whose dispatcher stopped watching it to be bounded by the same wall budget
  So that no run holds a factory slot forever because its watcher gave up

  Background:
    Given an item active with assignee fabro, attributed by its run stamp to this host and a declared factory
    And the factory reports the stamped run running, with the instant it first reported it running in the run's own record
    And every ownership lock location for the item on this host was read and none is held by a live process

  Scenario: An unowned run past its budget and not progressing is exported, cancelled and rested for a human
    Given the run's slot-holding time is strictly greater than the resolved whole-run wall budget
    And the run created no work-in-progress capture and completed no new workflow node within its progress window
    When a reconcile-runs pass runs
    Then the run's preserve-by-reference pointer is written and read back before the run is cancelled
    And one run-wall-budget-exceeded record names the run, the elapsed seconds, the budget and the pointer
    And the item rests at blocked with blocked_reason needs-human and a ledger comment naming the remedy resolve-blocked

  Scenario: An unowned run within its budget is held
    Given the run's slot-holding time is not greater than the resolved whole-run wall budget
    When a reconcile-runs pass runs
    Then the run is not cancelled
    And the pass lists the claim in held with the reason run-live

  Scenario: A run whose ownership lock a live process holds is left to its own watch
    Given a live process holds the item's ownership lock
    And the run's slot-holding time is strictly greater than the resolved whole-run wall budget
    When a reconcile-runs pass runs
    Then the run is not cancelled by the pass
    And the pass lists the claim in held with the reason run-live

  Scenario: An unowned run whose record carries no running instant is never cancelled on an unmeasured budget
    Given the run's own record carries no instant at which it was first reported running
    When a reconcile-runs pass runs
    Then the run is not cancelled
    And the pass lists the claim in held with the reason run-live

  Scenario: An unowned run whose export cannot be read back is held, not cancelled
    Given the run's slot-holding time is strictly greater than the resolved whole-run wall budget and the run is not progressing
    And the preserve-by-reference pointer cannot be read back and no verified preservation ref of the run exists
    When a reconcile-runs pass runs
    Then the run is not cancelled
    And one run-wall-budget-held record names the run and the failed measurement
    And the pass lists the claim in held with the reason run-live

  Scenario: The host's periodic pass bounds another dispatching repository's unowned run
    Given the run was dispatched by another repository the host's plugin install registry names
    And that repository's ledger and ownership lock locations are readable
    And the run's slot-holding time is strictly greater than the resolved whole-run wall budget and the run is not progressing
    When the periodic reconcile-runs pass started from this repository runs
    Then the run is exported, cancelled and recorded with run-wall-budget-exceeded
    And the item rests at blocked with blocked_reason needs-human in the ledger of the repository that dispatched it

  Scenario: A dispatch that stops observing its run hands the budget to reconciliation
    Given a dispatch's re-attach supervision can no longer read its bound run and retains the item's claim
    When the dispatch ends
    Then its outcome record names the run and the factory
    And states that the run's whole-run wall budget is left to reconciliation
```

Co-edit owed at revise, outside this spec target: tests/heading-coverage.json MUST gain one row for the new `## Scenario 349` heading (test `TODO`, with a reason that names the owed scenario-tier test and the live work-item bd-ib-ag633q that owns landing it), per the repository's heading-coverage co-edit rule.
