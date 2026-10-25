---
topic: reconcile-merged-locally-built-item-entry
author: claude-opus-5-5
created_at: 2026-10-25T03:24:57Z
---

## Proposal: reconcile-merged accepts a merged, locally built item resting at pending-approval or ready

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

reconcile-merged's accepted statuses widen to an item resting at pending-approval, or at ready without recovery routing, that was built outside the factory and is carried by a merged pull request identified by head ref or title. The same janitor and acceptance path apply, with the resting status in place of active.

### Motivation

Work-item bd-ib-acxptq, stability tier (epic livespec-dev-tooling-dfixhe). bd-ib-y7372n was built locally, never dispatched, and merged while resting at pending-approval. reconcile-merged refuses anything that is not active, in acceptance, or ready with merged recovery routing, so the only close route was a hand-written move to active. Approval is not the gap here (dispatcher.auto_approve_ready is true); the missing entry is.

### Proposed Changes

In SPECIFICATION/contracts.md section "Dispatcher loop invocation surface", replace:

rests at `ready` with recovery routing holding its next dispatch because the
pull request of its latest dispatch is merged (§"Factory-configurable ACP
fallback priority" → "Recovery from the failed run's preserved work").

with:

rests at `ready` with recovery routing holding its next dispatch because the
pull request of its latest dispatch is merged (§"Factory-configurable ACP
fallback priority" → "Recovery from the failed run's preserved work"), or rests
at `pending-approval` or at `ready` without such routing because it was built
outside the factory and a merged pull request carries it. For such a locally
built item, the merged pull request MUST resolve from the head-ref or title tier
of the resolution below; a pull request that only mentions the item in its body
MUST NOT resolve it, and the valve MUST refuse naming the missing merged pull
request. The valve then applies every guard and the post-merge disposition below
exactly as for an `active` item, with the item's resting status in place of
`active` in each state effect: a green janitor writes `pending-approval ->
acceptance` or `ready -> acceptance`, and every failed guarded precondition
leaves the item at its resting status. Scenario 245 in `scenarios.md`
exercises this entry.

and replace:

missing merged PR, wrong source lane, ambiguous merged PR, or held janitor
checkout lock MUST leave the item `active` and report the failed guarded
precondition or janitor stage.

with:

missing merged PR, wrong source lane, ambiguous merged PR, or held janitor
checkout lock MUST leave the item `active` (or at its resting status, for an
item that entered at `pending-approval` or `ready`) and report the failed
guarded precondition or janitor stage.

Append to SPECIFICATION/scenarios.md:

## Scenario 245 — reconcile-merged closes a merged, locally built item resting at pending-approval or ready

```gherkin
Feature: A merged item built outside the factory has a guarded close path
  As the operator closing an item that was implemented locally and merged
  I want reconcile-merged to accept it from the status it rests at
  So that closing it does not need a hand-written move to active

  Scenario: A pending-approval item with a merged pull request enters acceptance
    Given an item resting at pending-approval
    And a merged pull request on the default branch that identifies the item by head ref or title
    When reconcile-merged runs for the item and its post-merge janitor is green
    Then the item moves from pending-approval to acceptance
    And the post-merge acceptance pass runs

  Scenario: A ready item without recovery routing and with a merged pull request enters acceptance
    Given an item resting at ready with no recovery routing
    And a merged pull request on the default branch that identifies the item by head ref or title
    When reconcile-merged runs for the item and its post-merge janitor is green
    Then the item moves from ready to acceptance
    And the post-merge acceptance pass runs

  Scenario: A body mention alone does not close a locally built item
    Given an item resting at pending-approval or ready
    And no merged pull request that identifies the item by head ref or title
    When reconcile-merged runs for the item
    Then it refuses naming the missing merged pull request
    And the item stays at the status it rested at

  Scenario: A red janitor leaves a locally built item where it rested
    Given an item resting at pending-approval or ready with a merged pull request that identifies it
    When reconcile-merged runs for the item and its post-merge janitor is red
    Then the item stays at the status it rested at
    And the refusal names the failing janitor stage
```

