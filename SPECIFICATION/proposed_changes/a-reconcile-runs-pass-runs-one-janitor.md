---
topic: a-reconcile-runs-pass-runs-one-janitor
author: claude-opus-5-5
created_at: 2026-11-14T13:04:20Z
---

## Proposal: A reconcile-runs pass runs at most one owed post-merge janitor, least recently attempted first, within its pass budget, and defers the rest with a named reason

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md §"Stranded claim release" hold 8 (`run-succeeded`) makes a reconciliation pass perform `reconcile-merged` in the same pass for every handed-off claim whose pull request the forge reports merged, and the ordinary arm of `reconcile-merged` runs the item's owed post-merge janitor. No clause bounds how many such janitors one pass runs, or how long, so a pass that finds several merged handed-off items runs their janitors back to back and outlives the host timer that started it. This proposal bounds the standalone `dispatcher.py reconcile-runs` sweep, and only that surface. One pass MUST run at most one owed post-merge janitor gate. It picks the owed item whose janitor was least recently attempted (never-attempted first), so a persistently red or timing-out item cannot keep the one slot. A new committed-configuration key, `dispatcher.reconcile_pass_budget_seconds` (default `1800`, the host timer's start timeout), gives the pass's wall budget. The pass runs its one janitor last and stops it at the remaining budget less a fixed 60 s margin. A janitor stopped there records the distinct verdict `timed-out`, stays owed, and counts as an attempt. Every other owed item is deferred to a later pass with its janitor still owed and is journaled by id with a reason naming the bound. The pass MUST then exit on its own status within the resolved budget. The loop tick and the dispatch preamble are deliberately unchanged. A new Scenario 374 exercises the rule.

### Motivation

Work item bd-ib-wonsmb (orchestrator ledger), ruled spec-change tier by legacy-coordinator-agent: no ratified H2 of this spec states a per-pass janitor bound, so the item cannot be approved until a proposal with a scenario lands. Measurement on host vmi3006760, 2026-11-14: the standalone `reconcile-runs` sweep runs under a host systemd timer whose unit declares `TimeoutStartSec=1800`. Passes that ran two or more `janitor-post-merge` gates in sequence overran 1800 s and were TERM-killed by systemd (10:50Z-11:20Z and 11:30Z-12:00Z, both `Result=timeout`). Each kill threw away the janitor in flight, so its item stayed owed and the next pass started the same work again. Passes that ran exactly one janitor took 24 min and 27.5 min and ended on their own. Memory was ruled out as the cause; the overrun is wall time spent in sequential janitors. The coordinator's ruling: do NOT raise the timeout; bound janitors per pass to one (or run janitors outside the pass). This proposal takes the per-pass bound. Because a single janitor alone measured up to 27.5 min against a 30 min timeout, one janitor per pass is not by itself a guarantee, so the pass also carries a wall budget that the Dispatcher enforces on the janitor it runs. Fairness: under `reconcile-merged` a red janitor leaves the item `active` (§"Dispatcher loop invocation surface", the guarded entry path), so hold 8 finds it owed again on every pass; ordering by merge time would spend every pass's one slot on the same persistently red item. Ordering by last janitor attempt prevents that starvation. Fleet scope: the rule governs every tenant whose `reconcile-runs` timer is enabled, because every such tenant runs this Dispatcher's sweep under the same 1800 s start timeout, and any of them can accumulate several merged handed-off items between passes. It governs the standalone `reconcile-runs` sweep only, the one reconciliation surface a host timer runs under a start timeout. The other surfaces that apply hold 8 per §"Stranded claim release" → "Survey" (the loop tick and the dispatch preamble) are deliberately unchanged. Placement: the obligation to run a janitor inside the pass comes from hold 8 of §"Stranded claim release", so the bound and its budget key belong beside it in that subsection, under §"Dispatcher policy settings". The "Reconciliation-pass reads" paragraph of §"Bounded Fabro event reads" already defines a reconciliation pass and bounds its journal reads; it governs reads, not janitor work, so this proposal reuses its definition of a pass by reference and does not edit it. In-flight alignment (survey of the 10 open spec-touching pull requests on 2026-11-14): none touches reconcile-runs janitor bounds or hold 8; every relationship is align. #5278 (v376) adds Scenario 373, so this proposal takes Scenario 374, the next number free across master, every pending proposal in SPECIFICATION/proposed_changes and every open spec pull request. Filed by legacy-dispatcher-agent on legacy-coordinator-agent's ruling; revised on that coordinator's NOT-READY grade of head 49eeb642b6 (starvation, the uncontrolled exit bound, and the surface scope).

### Proposed Changes

**1. The per-pass janitor bound and pass budget (`contracts.md` §"Dispatcher policy settings" → §"Stranded claim release").** Insert a new bullet immediately before the "**Holds.**" bullet:

> - **One post-merge janitor per pass.** This bullet governs the standalone `reconcile-runs` sweep only. A *reconciliation pass* is as §"Bounded Fabro event reads" → "Reconciliation-pass reads" defines it: one run of the standalone `dispatcher.py reconcile-runs` command, whether an operator or a host timer starts it. The loop tick and the dispatch preamble, the other surfaces "Survey" above names, MUST continue to apply hold 8 exactly as they do without this bullet; neither the bound nor the pass budget below applies to them.
>
>   *Owed janitors.* An item's post-merge janitor is *owed* in a pass when this subsection would have the pass run that janitor for the item, by any route; the same-pass `reconcile-merged` of hold 8 below is one such route, because its ordinary arm runs the item's post-merge janitor. A `reconcile-merged` arm that the clauses already forbid from re-running the janitor (the re-accept and regrade arms) owes none and is not counted. An item's *last janitor attempt* is the `started_at` of the newest `janitor-post-merge` row the dispatch journal holds for that item's merged pull request, whatever that row's verdict, read from the pass's one parsed snapshot of the journal; an item with no such row has never been attempted.
>
>   *The bound.* One reconciliation pass MUST run at most one owed post-merge janitor gate. When a pass finds more than one item whose janitor is owed, it MUST select exactly one of them, in this order: an item that has never been attempted before one that has; among attempted items, the oldest last janitor attempt first; remaining ties by the instant the forge reports the pull request merged, earliest first, then by ascending work-item id. Because every janitor that does not end green leaves an attempt behind it, an item whose janitor ends red, unrunnable or timed out goes behind every owed item attempted less recently, so a persistently failing item cannot hold the one slot ahead of the others. The one janitor counts against the bound whatever its result.
>
>   *Deferral.* Every other item whose janitor is owed in that pass MUST be deferred to a later pass: the pass MUST NOT run its janitor, MUST NOT perform its `reconcile-merged` or any other completion that would run that janitor, MUST NOT change its status or labels, and MUST leave its janitor owed, so that a later pass finds it owed again. The pass MUST list each deferred item in its `held` output as `run-succeeded` and MUST journal it by work-item id as a `stranded-claim-hold` row whose reason is `janitor-deferred-one-per-pass`, a reason that names this bound. A deferral is not a failure of the item and MUST NOT be recorded as a janitor result or as a janitor attempt.
>
>   *The pass budget.* `dispatcher.reconcile_pass_budget_seconds` is a positive integer of seconds for the wall budget of one reconciliation pass, measured from the pass's start. It documents, and MUST be set no greater than, the start timeout of the host timer that starts the pass (the fleet's reconcile-runs timer declares `TimeoutStartSec=1800`). It resolves through two layers, most specific last: the built-in default of **1800** seconds, then the repository's committed `.livespec.jsonc`. A non-positive or non-integer value MUST be refused as a configuration error naming the key, and the pass MUST then run no janitor. It is a committed-configuration-only key, like `dispatcher.require_invoker`: it carries no per-item override, because a pass budget is not a per-item property, and it is outside the API-configurable key set of §"Control surface and audit". The pass MUST journal the resolved budget and the layer that supplied it.
>
>   *Janitor last, bounded by the budget.* The pass MUST run its one janitor after every other piece of its work: the survey, every release, completion and hold of this subsection, and the run-side reconciliation of §"A factory run never awaits a human". The pass MUST bound that janitor's wall time to the budget remaining when the janitor starts, less a fixed margin of **60** seconds. When that bound is not positive, the pass MUST NOT start a janitor, and the item it would have selected is deferred like any other, its reason `janitor-deferred-pass-budget`. When the janitor's check suite has not reached a verdict at that bound, the pass MUST stop the suite in whichever venue it runs, MUST record the janitor's `janitor-post-merge` row with the distinct verdict `timed-out` (not red: the suite reached no verdict), MUST leave the item `active` and its janitor owed exactly as a red janitor leaves it, and the row's `started_at` is that item's last janitor attempt. Whatever its verdict, green, red, unrunnable or `timed-out`, the janitor the pass ran MUST record that verdict in the dispatch journal on the `janitor-post-merge` row the janitor rules of §"Dispatcher admission, WIP cap, and post-merge acceptance" already require.
>
>   *Exit.* After its janitor ends, or once it has decided to run none, the pass MUST finish its remaining journaling and exit on its own exit status within the resolved `dispatcher.reconcile_pass_budget_seconds` of its start. A pass MUST NOT end by the host timer's start-timeout TERM; this bound and its budget, not a longer timeout, are how the pass stays inside it. This bullet does not relax "Reconciliation-pass reads": the deferred items' journal reads and every last-attempt read still come from the pass's one parsed snapshot.

**2. Hold 8 defers to the bound on the standalone sweep (`contracts.md` §"Stranded claim release", "**Holds.**" item 8, `run-succeeded`).** Replace the sentence "When the forge reports the pull request merged and the preconditions of `reconcile-merged` hold, the Dispatcher MUST perform `reconcile-merged` for the item in the same pass, with no `resolve-blocked` and no `resume`." with:

> When the forge reports the pull request merged and the preconditions of `reconcile-merged` hold, the Dispatcher MUST perform `reconcile-merged` for the item in the same pass, with no `resolve-blocked` and no `resume`, unless, on the standalone `reconcile-runs` sweep, the bullet "One post-merge janitor per pass" above defers it; a deferred item stays held as `run-succeeded`, its held entry naming `janitor-deferred-one-per-pass` or `janitor-deferred-pass-budget`.

**3. Section scenario pointer (`contracts.md` §"Stranded claim release", closing line).** Replace "Scenarios 196, 210 and 349 in `scenarios.md` exercise this section." with "Scenarios 196, 210, 349 and 374 in `scenarios.md` exercise this section."

**4. Scenario (`scenarios.md`).** Append, after the highest-numbered scenario present when the revise cuts:

## Scenario 374 — A reconcile-runs pass runs at most one owed post-merge janitor, least recently attempted first, within its pass budget, and defers the rest with a named reason

Governing clause: `contracts.md` §"Stranded claim release" → "One post-merge janitor per pass".

```gherkin
Feature: One post-merge janitor per reconcile-runs pass, within the pass budget
  As the maintainer of a tenant whose reconcile-runs timer is enabled
  I want each standalone reconciliation pass to run at most one owed post-merge janitor inside its budget
  So that the host timer's start timeout never kills a janitor mid-run and no failing item starves the rest

  Background:
    Given the standalone reconcile-runs sweep
    And active fabro items whose newest dispatches succeeded and journaled merge-wait-handed-off
    And the forge reports each item's pull request merged and the preconditions of reconcile-merged hold for each

  Scenario: Three never-attempted owed janitors - one runs, two are deferred with a named reason
    Given items A, B and C with no janitor-post-merge row, A's pull request merged earliest
    When a reconcile-runs pass runs on the owning host
    Then the pass runs the post-merge janitor of A only, after all its other work
    And the dispatch journal carries a janitor-post-merge row for A recording its verdict
    And B and C keep their status and labels and still owe their janitor
    And held lists B and C as run-succeeded naming janitor-deferred-one-per-pass
    And the dispatch journal carries a stranded-claim-hold row for each of B and C, by id, with reason janitor-deferred-one-per-pass

  Scenario: A red janitor does not take the next pass's slot from a never-attempted item
    Given items A and B with no janitor-post-merge row, A's pull request merged earliest
    And A's janitor check suite fails
    When a reconcile-runs pass runs on the owning host
    Then the dispatch journal carries a janitor-post-merge row for A recording its red verdict
    And A stays active and still owes its janitor
    And held lists B as run-succeeded naming janitor-deferred-one-per-pass
    When the next reconcile-runs pass runs on the owning host
    Then that pass runs the post-merge janitor of B, not A
    And held lists A as run-succeeded naming janitor-deferred-one-per-pass

  Scenario: A janitor that outlasts the pass budget is stopped as timed-out and the pass exits on its own
    Given the repository commits dispatcher.reconcile_pass_budget_seconds 120
    And items A and B with no janitor-post-merge row, A's pull request merged earliest
    And A's janitor check suite never reaches a verdict
    When a reconcile-runs pass runs on the owning host
    Then the pass stops A's check suite no later than 60 seconds before the 120-second budget ends
    And the dispatch journal carries a janitor-post-merge row for A with verdict timed-out
    And A stays active and still owes its janitor
    And the pass exits on its own exit status within 120 seconds of its start, not by a timeout TERM
    When the next reconcile-runs pass runs on the owning host
    Then that pass runs the post-merge janitor of B, not A

  Scenario: A pass with no budget left for a janitor runs none
    Given the repository commits dispatcher.reconcile_pass_budget_seconds 60
    And item A with no janitor-post-merge row
    When a reconcile-runs pass runs on the owning host
    Then the pass runs no post-merge janitor
    And held lists A as run-succeeded naming janitor-deferred-pass-budget
    And the pass exits on its own exit status within 60 seconds of its start

  Scenario: The loop tick is not bounded
    Given items A and B with no janitor-post-merge row
    When a loop tick reconciles stranded claims
    Then the loop tick applies hold 8 to both A and B exactly as it does without the one-janitor bound
```

**5. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new Scenario 374 heading (carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit), with `spec_root: "SPECIFICATION"`, `spec_file: "scenarios.md"`, `test: "TODO"`, `work_item: "bd-ib-wonsmb"` and a non-empty `reason` naming the tier the owed test runs at (integration or above: a reconcile-runs pass driven against a stub factory, forge and janitor check suite with several merged handed-off items and a small committed pass budget), and one matching `tests/heading-coverage-debt.json` entry carrying `spec_root`, `spec_file` and `heading`, `work_item: "bd-ib-wonsmb"` and `first_seen` set to the revise date. This proposal adds no new `## ` heading to `contracts.md`; the new bullet and its key sit inside the existing §"Stranded claim release" subsection. If the revise renumbers Scenario 374 because a higher number has landed first, the scenario heading, the §"Stranded claim release" pointer of change 3, the heading-coverage row and the debt entry MUST all carry the renumbered heading text.
