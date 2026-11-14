---
topic: a-reconcile-runs-pass-runs-one-janitor
author: claude-opus-5-5
created_at: 2026-11-14T13:04:20Z
---

## Proposal: A reconcile-runs pass runs at most one owed post-merge janitor and defers the rest with a named reason

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md §"Stranded claim release" hold 8 (`run-succeeded`) makes a reconciliation pass perform `reconcile-merged` in the same pass for every handed-off claim whose pull request the forge reports merged, and the ordinary arm of `reconcile-merged` runs the item's owed post-merge janitor. No clause bounds how many such janitors one pass runs, so a pass that finds several merged handed-off items runs their janitors back to back and outlives the host timer that started it. This proposal adds a per-pass bound: one standalone `dispatcher.py reconcile-runs` pass MUST run at most one owed post-merge janitor gate. Every other owed item is deferred to a later pass with its janitor still owed, and the pass journals each deferred item by id with a reason naming the bound. The pass MUST end on its own exit status inside the host timer's 1800 s start timeout, and the janitor it ran MUST record a verdict. A new Scenario 374 exercises the rule.

### Motivation

Work item bd-ib-wonsmb (orchestrator ledger), ruled spec-change tier by legacy-coordinator-agent: no ratified H2 of this spec states a per-pass janitor bound, so the item cannot be approved until a proposal with a scenario lands. Measurement on host vmi3006760, 2026-11-14: the standalone `reconcile-runs` sweep runs under a host systemd timer whose unit declares `TimeoutStartSec=1800`. Passes that ran two or more `janitor-post-merge` gates in sequence overran 1800 s and were TERM-killed by systemd (10:50Z-11:20Z and 11:30Z-12:00Z, both `Result=timeout`). Each kill threw away the janitor in flight, so its item stayed owed and the next pass started the same work again. Passes that ran exactly one janitor took 24 min and 27.5 min and ended on their own. Memory was ruled out as the cause; the overrun is wall time spent in sequential janitors. The coordinator's ruling: do NOT raise the timeout; bound janitors per pass to one (or run janitors outside the pass). This proposal takes the per-pass bound, which keeps a pass's wall time at one janitor plus the sweep's own reads, and needs no change to any host unit. Fleet scope: the rule governs every tenant whose `reconcile-runs` timer is enabled, because every such tenant runs this Dispatcher's sweep under the same 1800 s start timeout, and any of them can accumulate several merged handed-off items between passes. Placement: the obligation to run a janitor inside the pass comes from hold 8 of §"Stranded claim release" (the same-pass `reconcile-merged` for a `merge-wait-handed-off` claim), so the bound belongs beside it in that subsection. The "Reconciliation-pass reads" paragraph of §"Bounded Fabro event reads" already defines a reconciliation pass and bounds its journal reads; it governs reads, not janitor work, so this proposal reuses its definition of a pass by reference and does not edit it. In-flight alignment (survey of the 10 open spec-touching pull requests on 2026-11-14): none touches reconcile-runs janitor bounds or hold 8; every relationship is align. #5278 (v376) adds Scenario 373, so this proposal takes Scenario 374, the next number free across master, every pending proposal in SPECIFICATION/proposed_changes and every open spec pull request. Filed by legacy-dispatcher-agent on legacy-coordinator-agent's ruling.

### Proposed Changes

**1. The per-pass janitor bound (`contracts.md` §"Dispatcher policy settings" → §"Stranded claim release").** Insert a new bullet immediately before the "**Holds.**" bullet:

> - **One post-merge janitor per pass.** A *reconciliation pass* is as §"Bounded Fabro event reads" → "Reconciliation-pass reads" defines it: one run of the standalone `dispatcher.py reconcile-runs` command, whether an operator or a host timer starts it. An item's post-merge janitor is *owed* in a pass when this subsection would have the pass run that janitor for the item, by any route; the same-pass `reconcile-merged` of hold 8 below is one such route, because its ordinary arm runs the item's post-merge janitor. A `reconcile-merged` arm that the clauses already forbid from re-running the janitor (the re-accept and regrade arms) owes none and is not counted. One reconciliation pass MUST run at most one owed post-merge janitor gate. When a pass finds more than one item whose janitor is owed, it MUST run the janitor of exactly one of them: the item whose pull request the forge reports merged earliest, ties broken by ascending work-item id, so that a deferred item cannot be passed over indefinitely by items merged after it. The one janitor counts against the bound whatever its result: a red or unrunnable janitor is still the pass's one janitor. Every other item whose janitor is owed in that pass MUST be deferred to a later pass: the pass MUST NOT run its janitor, MUST NOT perform its `reconcile-merged` or any other completion that would run that janitor, MUST NOT change its status or labels, and MUST leave its janitor owed, so that a later pass finds it owed again. The pass MUST list each deferred item in its `held` output as `run-succeeded` and MUST journal it by work-item id as a `stranded-claim-hold` row whose reason is `janitor-deferred-one-per-pass`, a reason that names this bound. A deferral is not a failure of the item and MUST NOT be recorded as a janitor result. The janitor the pass did run MUST record its verdict in the dispatch journal as the `janitor-post-merge` row the janitor rules of §"Dispatcher admission, WIP cap, and post-merge acceptance" already require, carrying its green, red or unrunnable result. Because the pass runs at most one janitor, it MUST end on its own exit status within the start timeout of the host timer that starts it (the fleet timer declares `TimeoutStartSec=1800`); a pass MUST NOT end by that timer's timeout TERM, and this bound, not a longer timeout, is how the pass stays inside it. This bullet does not relax "Reconciliation-pass reads": the deferred items' journal reads still come from the pass's one parsed snapshot.

**2. Hold 8 defers to the bound (`contracts.md` §"Stranded claim release", "**Holds.**" item 8, `run-succeeded`).** Replace the sentence "When the forge reports the pull request merged and the preconditions of `reconcile-merged` hold, the Dispatcher MUST perform `reconcile-merged` for the item in the same pass, with no `resolve-blocked` and no `resume`." with:

> When the forge reports the pull request merged and the preconditions of `reconcile-merged` hold, the Dispatcher MUST perform `reconcile-merged` for the item in the same pass, with no `resolve-blocked` and no `resume`, unless the bullet "One post-merge janitor per pass" above defers it; a deferred item stays held as `run-succeeded`, its held entry naming `janitor-deferred-one-per-pass`.

**3. Section scenario pointer (`contracts.md` §"Stranded claim release", closing line).** Replace "Scenarios 196, 210 and 349 in `scenarios.md` exercise this section." with "Scenarios 196, 210, 349 and 374 in `scenarios.md` exercise this section."

**4. Scenario (`scenarios.md`).** Append, after the highest-numbered scenario present when the revise cuts:

## Scenario 374 — A reconcile-runs pass runs at most one owed post-merge janitor and defers the rest with a named reason

Governing clause: `contracts.md` §"Stranded claim release" → "One post-merge janitor per pass".

```gherkin
Feature: One post-merge janitor per reconcile-runs pass
  As the maintainer of a tenant whose reconcile-runs timer is enabled
  I want each reconciliation pass to run at most one owed post-merge janitor
  So that the host timer's 1800 s start timeout never kills a janitor mid-run

  Background:
    Given a tenant whose reconcile-runs pass is started by a host timer with a 1800 s start timeout

  Scenario: Three owed janitors - one runs, two are deferred with a named reason
    Given three active fabro items whose newest dispatches succeeded and journaled merge-wait-handed-off
    And the forge reports each item's pull request merged, the first item's earliest
    And the preconditions of reconcile-merged hold for each item
    When a reconcile-runs pass runs on the owning host
    Then the pass runs the post-merge janitor of the first item only
    And the dispatch journal carries a janitor-post-merge row for the first item recording its verdict
    And the second and third items keep their status and labels and still owe their janitor
    And held lists the second and third items as run-succeeded naming janitor-deferred-one-per-pass
    And the dispatch journal carries a stranded-claim-hold row for each of the second and third items, by id, with reason janitor-deferred-one-per-pass
    And the pass ends on its own exit status within the 1800 s start timeout, not by the timer's timeout TERM

  Scenario: A later pass runs the next deferred janitor
    Given the pass above deferred the second and third items
    When the next reconcile-runs pass runs on the owning host
    Then the pass runs the post-merge janitor of the second item only
    And held lists the third item as run-succeeded naming janitor-deferred-one-per-pass

  Scenario: A red janitor still uses the pass's one janitor
    Given two active fabro items whose janitors are owed in the same pass
    And the janitor of the earlier-merged item fails
    When a reconcile-runs pass runs on the owning host
    Then the dispatch journal carries a janitor-post-merge row for the earlier-merged item recording its red verdict
    And the pass runs no janitor for the other item
    And held lists the other item as run-succeeded naming janitor-deferred-one-per-pass
```

**5. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new Scenario 374 heading (carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit), with `spec_root: "SPECIFICATION"`, `spec_file: "scenarios.md"`, `test: "TODO"`, `work_item: "bd-ib-wonsmb"` and a non-empty `reason` naming the tier the owed test runs at (integration or above: a reconcile-runs pass driven against a stub factory and forge with several merged handed-off items), and one matching `tests/heading-coverage-debt.json` entry carrying `spec_root`, `spec_file` and `heading`, `work_item: "bd-ib-wonsmb"` and `first_seen` set to the revise date. This proposal adds no new `## ` heading to `contracts.md`; the new bullet sits inside the existing §"Stranded claim release" subsection. If the revise renumbers Scenario 374 because a higher number has landed first, the scenario heading, the §"Stranded claim release" pointer of change 3, the heading-coverage row and the debt entry MUST all carry the renumbered heading text.
