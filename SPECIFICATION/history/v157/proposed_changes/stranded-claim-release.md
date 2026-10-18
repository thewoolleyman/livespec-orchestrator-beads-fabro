---
topic: stranded-claim-release
author: claude-opus-5-5:run-lifecycle-false-verdicts
created_at: 2026-10-18T04:08:18Z
---

## Proposal: Stranded dispatch claim release

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the claim half of run reconciliation. reconcile-runs (and every reconciliation surface) surveys the ledger's active items assigned fabro, asks each claim's journaled run of its declared factory, and releases a stranded claim to ready (reason run-absent or run-terminal) only on positive evidence that no run and no live dispatch remains and no merged pull request exists, while every claim it cannot prove stranded is held in held with one named reason. Today the reconciler is run-centric, so a claim whose run is gone is invisible to it and only a hand move valve recovers the item.

### Motivation

The spec names reconcile-runs as the remedy for a stranded claim (contracts.md, resume refusal), and the dispatcher's 'already claimed by a dispatch' refusal says the same, but §"A factory run never awaits a human" only reconciles runs that still exist and forbids reconciliation from changing item status. So a claim whose run vanished, through a provider spend-limit kill (2026-09-08: livespec-dev-tooling-2hno, -x7ml, -sh71), overload kills, Docker restarts and a fabro-server restart (2026-10-12: tb2az6, psqaav three times), or an engine cycle-cap ending (2026-10-18: bd-ib-l55d7e, run 01M55X0ZNKTFXC1J8D9MT6WBF4), stays active/fabro until an operator runs drive move:<id>:ready. Work-item bd-ib-m0t0 owns the implementation, and its Definition of Done needs a governing scenario: the factory dod_gate refuses a reference that resolves but does not state the behaviour.

### Proposed Changes

Add a new subsection to SPECIFICATION/contracts.md, placed directly after §"A factory run never awaits a human" and before §"The human answer route: marker, poison preflight, run account, and write-before-transition ordering":

### Stranded claim release

§"A factory run never awaits a human" reconciles the RUN half of the invariant that, on every declared factory, the set of non-terminal runs equals the set of work-items that are `active` under a live dispatch claim whose journaled run id is that run. This subsection reconciles the CLAIM half. A dispatch claim is a work-item resting at `active` with assignee `fabro`. A claim is STRANDED when its journaled run is no longer a live run on its factory and no live dispatch is watching the item. Examples: the run was removed with `fabro rm --force`, the factory server restarted under it, or the run reached a terminal status while the Dispatcher that owned it was killed before it wrote a terminal outcome.

- **Claim-side survey.** Every reconciliation surface named in §"A factory run never awaits a human" (loop tick, dispatch preamble, and the standalone `reconcile-runs` sweep) MUST also enumerate the ledger's `active` items assigned `fabro`. For each one, it MUST resolve the claim's journaled run id and factory from the item's newest dispatch-journal run stamp, and MUST ask that factory for that run by the factory's declared server target. An item carrying `rework:pending` or a `merge-hold:` label MUST NOT be surveyed, per §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Stranded-state discrimination".
- **Live dispatch lock.** "A live dispatch holds the item" means a dispatch-scoped ownership lock for the item (§"Dispatcher loop invocation surface") whose process id is alive exists in ANY checkout of the tenant's repository, not only the checkout the sweep runs from.
- **Release.** The Dispatcher MUST release a stranded claim by returning the item to `ready` and clearing its `fabro` assignee. It MUST journal one `stranded-claim-release` record naming the item, the run id, the factory and the reason, and it MUST write a ledger comment on the item carrying the same facts. A claim is released with reason `run-absent` when the factory is reachable and its answer positively reports that the run does not exist. A claim is released with reason `run-terminal` when the run's status is terminal and not succeeded, no live dispatch holds the item, and the forge reports no merged pull request for the item. A `run-terminal` claim whose run failure the Dispatcher classifies under §"Factory-configurable ACP fallback priority" (provider-limit or adapter launch) MUST instead take that section's release route, so the claim keeps that section's hold and reason. Before releasing a `run-absent` claim, the Dispatcher MUST ask the forge whether a merged pull request for the item exists, as it does for `run-terminal`.
- **Hold.** Every claim the pass surveys and does not release MUST be left exactly as it is and MUST be listed in the pass's `held` output with exactly one reason:
  - `run-live`: the run is non-terminal.
  - `dispatch-live`: a live dispatch holds the item.
  - `run-succeeded`: the run is terminal and succeeded. The recovery is `reconcile-merged`, never a release.
  - `merged-pr`: the forge reports a merged pull request for the item. The recovery is `reconcile-merged`.
  - `factory-unobservable`: the factory could not be reached, or its answer could not be read.
  - `forge-unobservable`: the forge could not be asked.
  An unobservable measurement MUST hold the claim and MUST NOT release it. Stranded claims join `held` beside the parked runs the blocked-run grace already lists there. A pass whose `held` names no claim therefore means that no surveyed claim is stranded.
- **The one ledger change reconciliation makes.** A stranded-claim release is the only status change any reconciliation surface makes. The bullet of §"A factory run never awaits a human" that forbids reconciling or terminating a run from changing an item's status continues to govern runs, and does not govern this release. The `already claimed by a dispatch` refusal, and the resume refusal of §"Resume from a published pull request (`resume --item`)", name `reconcile-runs` as the remedy for a stranded claim; this subsection is what makes that remedy work.

Scenario 193 in `scenarios.md` exercises this section.

Add to SPECIFICATION/scenarios.md, after Scenario 192:

## Scenario 193 — Reconciliation releases a stranded dispatch claim, and holds with a named reason every claim it cannot prove stranded

```gherkin
Feature: The claim half of run reconciliation
  As a maintainer whose dispatch died without writing a terminal outcome
  I want reconciliation to release a claim whose run is gone
  So that the item can be re-dispatched without a hand move valve, and a claim that may still be live is never released

  Scenario: A claim whose run its factory reports absent is released
    Given an item active with assignee fabro whose journaled run the declared factory, queried by its server target, reports as not existing
    And no merged pull request exists for the item
    When a reconcile-runs pass runs
    Then the item is ready with no fabro assignee
    And one stranded-claim-release record names the item, the run id, the factory and the reason run-absent

  Scenario: A claim whose run failed with no live dispatch is released
    Given an item active with assignee fabro whose journaled run is terminal and not succeeded
    And no live dispatch lock for the item exists in any checkout of the tenant
    And no merged pull request exists for the item
    When a reconcile-runs pass runs
    Then the item is ready with no fabro assignee
    And one stranded-claim-release record names the reason run-terminal

  Scenario: A claim that may still be live, or that already merged, is held with its reason
    Given an item active with assignee fabro
    And its run is non-terminal, or a live dispatch lock holds it, or its run succeeded, or a merged pull request exists for it, or its factory or the forge cannot be observed
    When a reconcile-runs pass runs
    Then the item stays active with assignee fabro
    And the pass lists the claim in held with exactly one of run-live, dispatch-live, run-succeeded, merged-pr, factory-unobservable or forge-unobservable

  Scenario: A pass with no stranded claim lists no claim in held
    Given every active item assigned fabro has a non-terminal run on its declared factory
    When a reconcile-runs pass runs
    Then held names no claim with a release reason
    And no item changes status
```

