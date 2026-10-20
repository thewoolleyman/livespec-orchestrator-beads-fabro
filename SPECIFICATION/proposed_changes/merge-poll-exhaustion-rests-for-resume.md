---
topic: merge-poll-exhaustion-rests-for-resume
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:22:44Z
---

## Proposal: An exhausted merge-poll budget on an open pull request rests the item for resume, as a conflict does

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Since v145, "Armed pull request overtaken by the default branch" rests an item whose armed pull request conflicts at `blocked / needs-human`, with the recovery chain `resolve-blocked` then `resume`. But it says "An exhausted poll budget on a pull request the forge does not report as conflicting keeps its existing outcome", and that outcome leaves the item `active` under the `fabro` claim after its run has ended. That contradicts the run/claim invariant of "Stranded claim release", and no reconciler releases it, because terminal-run completion covers only runs that did not succeed. This proposal replaces that sentence. An exhausted budget on a pull request still OPEN rests the item the same way, under the named cause `merge-poll-budget-exhausted`. A pull request the forge reports MERGED at expiry proceeds as a merge observed in time.

### Motivation

Work-items bd-ib-l6rleb and bd-ib-ddu6wq, and the superseded bd-ib-y1b7. Measured 2026-10-16 on bd-ib-3hpdvm (run 01M51YS9C3A9 succeeded, PR 3106 armed, merge-poll ended at about 12:18Z, item left active/fabro) and 2026-10-17 on bd-ib-wvj4rk (run 01M52ZNAK6K7 succeeded, PR 3149 OPEN, item left active). On 2026-08-21, overseer-vkaa's PR merged 1h49m after the Dispatcher declared merge-poll failure. Each instance needed a human to find the stale claim. Plan spec-implementation-lockstep R1 batch 5 routes these here, generalizing the ratified v145 rest rather than adding a second recovery route.

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph beginning "**Armed pull request overtaken by the default branch.**", replace the sentence "An exhausted poll budget on a pull request the forge does not report as conflicting keeps its existing outcome." with:

> When the poll budget is exhausted, the Dispatcher MUST read the pull request's state once more before it records an outcome. A pull request the forge then reports MERGED MUST proceed exactly as a merge observed within the budget. A pull request the forge reports still OPEN and not in conflict MUST rest the item exactly as above, at `blocked` with `blocked_reason: needs-human`, through the same transition, journal row, ledger comment rules and recovery chain, with the named cause `merge-poll-budget-exhausted` in place of `base-advanced-after-arming` and the comment's marker line `livespec-merge-poll-budget-exhausted`. The item MUST NOT be left `active` under a claim whose run has ended. Scenario 220 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 220 — An exhausted merge-poll budget on an open pull request rests the item for resume

```gherkin
Feature: A succeeded run never strands its claim while its pull request waits
  As an operator whose armed pull request merges slowly
  I want an exhausted merge wait to rest the item where resume can reach it
  So that no claim sits active with no run behind it

  Scenario: An open, non-conflicting pull request rests the item
    Given a run that succeeded and armed auto-merge on its pull request
    And the merge wait's poll budget is exhausted while the forge reports the pull request OPEN and not in conflict
    When the Dispatcher records the outcome
    Then the item rests at blocked with blocked_reason needs-human and the cause merge-poll-budget-exhausted
    And the outcome detail names resolve-blocked then resume as the recovery chain

  Scenario: A pull request merged at expiry is not rested
    Given the poll budget is exhausted
    And the forge reports the pull request MERGED on the final read
    When the Dispatcher records the outcome
    Then it proceeds exactly as for a merge observed within the budget
```


## Proposal: A resume refusal on an active item names a remedy that changes that item's state

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A resume of a non-`ready` item refuses naming a remedy: `resolve-blocked` for an item at `blocked / needs-human`, or `reconcile-runs` for a stranded claim. For an `active` item whose run has ENDED, which stranded-claim release does not reconcile (a succeeded run), `reconcile-runs` releases nothing, so the named remedy is a no-op. This proposal requires the named remedy to be one that changes that item's state, and states the two missing arms: `reconcile-merged` when the forge reports the item's pull request merged, otherwise `move:<id>:ready`.

### Motivation

Work-items bd-ib-mzyhn2, bd-ib-l6rleb (its third assertion) and bd-ib-ddu6wq (its third assertion). Measured on build 3a2a826a8ac4 (v0.201.0): bd-ib-un7ch2 sat active/fabro after run 01M4ZMYSHNE6 succeeded. Its resume refused, naming reconcile-runs, and a tenant-wide reconcile-runs dry run returned reconciled [] and held [] for it. The valve that does release such a claim is move:<id>:ready. bd-ib-dbmoeh shows why the forge must be read first: move:<id>:ready on a merged item rebuilds merged work. Plan spec-implementation-lockstep R1 batch 5 routes these here as an amendment of the existing refusal bullet.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Resume from a published pull request (`resume --item`)", paragraph "**Refusals.**", replace "(remedy: `resolve-blocked:<id>:ready` for an item resting at `blocked / needs-human`, or `reconcile-runs` for a stranded claim)" with:

> (remedy: `resolve-blocked:<id>:ready` for an item resting at `blocked / needs-human`; `reconcile-runs` for a stranded claim that §"Stranded claim release" reconciles; and, for an `active` item whose run is terminal and which that release does not reconcile, `reconcile-merged` when the forge reports the item's pull request merged, otherwise `move:<id>:ready`). The named remedy MUST be one that changes that item's state; a refusal MUST NOT name a remedy that would leave the item unchanged.

and append to that bullet: "Scenario 221 in `scenarios.md` exercises the remedy rule."

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 221 — A resume refusal on an active item names a remedy that changes it

```gherkin
Feature: A refusal never sends the operator to a valve that does nothing
  As an operator resuming an item
  I want the refusal's remedy to act on the item as it stands
  So that following the remedy releases the item

  Scenario: An active item with a succeeded run and an unmerged pull request
    Given an item at active with assignee fabro whose run succeeded and is terminal
    And the forge reports its pull request open
    When dispatcher resume is invoked for it
    Then the refusal names move:<id>:ready and does not name reconcile-runs

  Scenario: An active item whose pull request merged
    Given an item at active with assignee fabro whose run is terminal
    And the forge reports its pull request merged
    When dispatcher resume is invoked for it
    Then the refusal names reconcile-merged
```


## Proposal: A capacity handoff reads the forge before advertising a status move for a claim with no recorded pull request

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Orchestrator-owned attention facts" forbids a capacity handoff from advertising a status-move action against a claim whose dispatch EVIDENCE shows a merged pull request. When the dispatching process died before it recorded the pull request, the evidence shows none, so the handoff advertises `move:<id>:ready` for work that is already merged. This proposal extends the rule: when the evidence names no pull request, the handoff MUST read the forge for the item's publish branch first, and a merged pull request found there routes to `reconcile-merged` exactly as recorded evidence does.

### Motivation

Work-item bd-ib-dbmoeh, measured 2026-08-22 on bd-ib-62xaj3: run 01M0M9DEHMC4 succeeded and PR #1741 merged, but the dispatch died before writing the pull request back, and needs-attention recommended move:bd-ib-62xaj3:ready. bd-ib-gajho2 records what that produces: a second, empty PR that becomes the item's merge evidence. Stranded-claim release already consults the forge for its merged-pr reason; this extends the same discipline to the attention handoff. Plan spec-implementation-lockstep R1 batch 5 routes it here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Orchestrator-owned attention facts", replace the sentence "No capacity handoff MAY advertise a status-move action against a claim whose dispatch evidence shows a merged pull request — the ratified reconciliation route is `reconcile-merged`, and a move-to-`ready` handoff would re-queue merged work." with:

> No capacity handoff MAY advertise a status-move action against a claim whose dispatch evidence, or the forge, shows a merged pull request — the ratified reconciliation route is `reconcile-merged`, and a move-to-`ready` handoff would re-queue merged work. When the dispatch evidence names no pull request, the handoff MUST read the forge for the item's publish branch before it advertises any status move, and MUST advertise `reconcile-merged` when the forge reports a merged pull request there. A forge read that fails MUST NOT be read as no pull request: the handoff MUST then advertise no status move and name the failed read. Scenario 222 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 222 — A capacity handoff for a claim with no recorded pull request reads the forge first

```gherkin
Feature: An attention handoff never re-queues merged work
  As an operator following a needs-attention handoff
  I want a merged pull request found on the forge to route to reconcile-merged
  So that a dispatch that died before recording its pull request is not rebuilt

  Scenario: A merged pull request found only on the forge
    Given a stranded claim whose dispatch evidence names no pull request
    And the forge reports a merged pull request on the item's publish branch
    When needs-attention composes its capacity handoff
    Then the handoff advertises reconcile-merged and no status move

  Scenario: An unreadable forge advertises no status move
    Given a stranded claim whose dispatch evidence names no pull request
    And the forge read fails
    When needs-attention composes its capacity handoff
    Then the handoff advertises no status move and names the failed forge read
```

