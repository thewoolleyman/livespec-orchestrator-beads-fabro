---
topic: reconcile-merged-runs-owed-janitor
author: claude-opus-5-5
created_at: 2026-10-22T06:19:50Z
---

## Proposal: reconcile-merged runs the post-merge janitor an acceptance item is still owed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Today `reconcile-merged --item` on an item resting in `acceptance` MUST NOT re-run the post-merge janitor and re-runs only the acceptance pass. That rule assumes the janitor already ran, because a green janitor is how an item normally reaches `acceptance`. The assumption is false on one designed route: when the janitor's checkout bootstrap fails after merge, the dispatch still writes `ledger-complete` and `acceptance-parked` and parks the item in `acceptance` with a needs-attention verdict saying the janitor did not run. Such an item can never leave `acceptance`, because the only valve for it refuses to run the janitor it is owed and no item-level janitor verb exists. This proposal narrows the prohibition: when the item's dispatch journal records that its post-merge janitor did not run, `reconcile-merged` runs that owed janitor against the merged default-branch tip, under every guard and the ownership lock that apply to an `active` item, and then re-runs the acceptance pass. It still never re-merges anything. An `acceptance` item whose janitor did run keeps today's acceptance-only behaviour.

### Motivation

Measured 2026-10-21 on openbrain `ob-5qlusq` (pull request openbrain#20, merged as `9dfaa0f5`), routed by coordinator ruling R480 and filed as bd-ib-ssmioz under plan epic bd-ib-6tcjfx. At 14:11:23Z the dispatch's `janitor-checkout-bootstrap` failed with `Justfile does not contain recipe install-commit-refuse-hooks` (the recipe was added later, in openbrain#21). The dispatch then wrote `ledger-complete` and `acceptance-parked`, with outcome needs-attention: "merged, but the post-merge janitor DID NOT RUN". `reconcile-merged --item ob-5qlusq` (gate 20261021T141533Z-3403233, build c6f61c5856ac) took the acceptance arm (`_reaccept_in_acceptance` in `commands/_dispatcher_reconcile_merged.py`), re-ran only acceptance, reported "janitor not re-run" and exited 1, leaving the item in `acceptance` with a NEEDS_ATTENTION verdict. The implementation obeys the ratified text exactly, so the fix is a spec change first. Prior art: bd-ib-lza6 (closed) introduced the valve; bd-ib-dd9l (closed) stranded merged items through a janitor-contract change, a different cause. In-flight work surveyed: the unmerged draft on `spec/reprove-merged-item-v2` adds a `resume --reprove` arm that re-proves a merged item's Proof of Done records; it does not touch the janitor, so this proposal aligns with it.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the paragraph that defines the guarded recovery surface `reconcile-merged --repo <path> --item <work-item-id>`, replace the sentence beginning "For an item resting in `acceptance` it MUST NOT re-run the post-merge janitor or re-merge anything" with the following text:

> For an item resting in `acceptance` it MUST NOT re-merge anything. Whether it runs the post-merge janitor depends on what that item's latest dispatch journaled about the janitor:
>
> - When the item's latest dispatch journaled that its post-merge janitor did NOT run, the item is still OWED that janitor. That is the case when the janitor checkout's bootstrap failed after the merge and the dispatch parked the merged item in `acceptance` with a needs-attention verdict saying the janitor did not run. The valve MUST then run that owed post-merge janitor against the merged default-branch tip, under every guard, the dispatch-scoped ownership lock and the janitor rules that apply to an `active` item, and journal the janitor's result against that dispatch. Only on a green janitor MUST it then re-run the acceptance pass described below. A red or unrunnable owed janitor MUST leave the item in `acceptance` with a needs-attention verdict naming the janitor stage and its failing target or bootstrap error. It MUST NOT close the item, MUST NOT re-run acceptance on that attempt, and MUST exit non-zero.
> - Otherwise, the janitor already ran, and the valve MUST NOT re-run it. It MUST re-run only the acceptance pass of §"Post-merge acceptance (`acceptance → done`)" against the records now on the pull request, apply that pass's ordinary disposition, and write a missing Proof of Done pointer (§"Proof of Done record" → "The pointer"). This is the route by which a host-leg record posted after the original pass reaches a verdict.
>
> The valve MUST decide which case applies from the dispatch journal's record of the janitor, never from the item's status alone. When the journal cannot be read, or carries no janitor record for the latest dispatch, it MUST refuse and name the missing evidence rather than guess either way.

The acceptance pass re-run in the second bullet is the same pass the first bullet re-runs after a green owed janitor.

In `SPECIFICATION/scenarios.md`, add:

```gherkin
## Scenario 237 — reconcile-merged runs the post-merge janitor a merged acceptance item is still owed

Feature: A merged item parked before its janitor ran can still reach a verdict
  As an operator recovering a merged work-item
  I want reconcile-merged to run the janitor the item is owed
  So that a bootstrap failure after merge does not strand the item in acceptance

  Scenario: An owed janitor runs, then acceptance re-runs
    Given a work-item resting in acceptance whose pull request is merged
    And its latest dispatch journaled that the post-merge janitor did not run because the janitor checkout bootstrap failed
    When reconcile-merged --item runs for that item and the janitor is green on the merged default-branch tip
    Then the post-merge janitor runs against the merged default-branch tip under the ownership lock
    And the janitor result is journaled against that dispatch
    And the acceptance pass re-runs and applies its ordinary disposition
    And nothing is merged again

  Scenario: A red owed janitor keeps the item in acceptance
    Given a work-item resting in acceptance whose latest dispatch journaled that the post-merge janitor did not run
    When reconcile-merged --item runs and the owed janitor fails
    Then the item stays in acceptance with a needs-attention verdict naming the janitor stage and its failing target
    And the acceptance pass does not re-run
    And the command exits non-zero

  Scenario: A janitor that already ran is not re-run
    Given a work-item resting in acceptance whose latest dispatch journaled a green post-merge janitor
    When reconcile-merged --item runs for that item
    Then the post-merge janitor does not run
    And only the acceptance pass re-runs

  Scenario: Missing janitor evidence refuses
    Given a work-item resting in acceptance whose latest dispatch has no journaled janitor record
    When reconcile-merged --item runs for that item
    Then the command refuses, naming the missing janitor evidence
    And no janitor runs and the acceptance pass does not re-run
```

In `tests/heading-coverage.json`, add an entry for that scenario heading with `test` set to `"TODO"` and a `reason` naming bd-ib-ssmioz as the owning work-item that adds the exercising test. If a concurrent revise has already taken Scenario 237, the revise pass renumbers this scenario to the next free number and updates the coverage entry to match.
