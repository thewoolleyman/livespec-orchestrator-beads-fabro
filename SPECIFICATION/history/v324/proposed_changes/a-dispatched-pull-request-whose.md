---
topic: a-dispatched-pull-request-whose
author: claude-opus-5-5
created_at: 2026-11-08T05:17:41Z
---

## Proposal: An exhausted merge wait hands an armed, passing pull request to reconciliation instead of resting it at needs-human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the merge wait's poll budget runs out and the forge reports the pull request OPEN, not in conflict, with auto-merge still armed and no required check failed, the Dispatcher stops resting the item at blocked/needs-human. It records a merge-wait handoff and leaves the item active under its claim, with the run's succeeded outcome behind it. The stranded-claim reconciliation pass then finishes the item: it runs reconcile-merged when the pull request merges, and routes a failed required check, or an unmerged close or disarm, the way those endings are routed today. The pull request's CI may take longer than any fixed budget, so the budget no longer decides whether a healthy pull request needs a human. Scenario 220 is retitled and rewritten to the new behaviour.

### Motivation

Work item bd-ib-bacahf, a child of plan factory-run-work-preservation (epic bd-ib-nckst7), filed on legacy-coordinator-agent's R301 order and routed back for this proposal on 2026-11-08 with fleet scope: the merge poll is shared by every member's dispatch, so a single orchestrator fix covers the fleet. The default budget is 80 polls × 30 s = 40 minutes. Current pull request CI in this repository takes about 30 to 40 minutes or more. On 2026-11-08 bd-ib-oknwxm's run 01M6VNKFXRA85Q8WF0JV23204B succeeded and armed auto-merge on pull request 4615. Its merge wait spent the budget at 00:15:53Z while CI run 42425491588 was still running coverage shards, and the item went to blocked/needs-human at 00:16:56Z although nothing was wrong with the pull request. The same night it struck bd-ib-csrvhs (pull request 4643) and bd-ib-ivm24w (pull request 4617). A resume would only poll again, so each instance cost a coordinator's hand close-out. Scenario 220 ratified the current rest because an item must not sit active under an ended claim where nothing reaches it. §"Stranded claim release" already holds such a claim as `run-succeeded` and names `reconcile-merged` as its recovery once the forge reports the merge. It does not perform that recovery, and this proposal makes it do so for a handed-off wait. §"Per-repo WIP cap" already excludes an `active` row whose dispatch reached a green terminal outcome, so the handoff costs no admission capacity. Of the two directions bd-ib-bacahf left open, a budget derived from measured CI duration is not chosen: any fixed or derived bound is overtaken by the next slow CI run, and it keeps a dispatching process alive for the whole wait. In-flight alignment: no open spec branch or pending proposal touches the merge wait, Scenario 220 or §"Stranded claim release".

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph that opens **Armed pull request overtaken by the default branch.**, replace the two sentences

> A pull request the forge reports still OPEN and not in conflict MUST rest the item exactly as above, at `blocked` with `blocked_reason: needs-human`, through the same transition, journal row, ledger comment rules and recovery chain, with the named cause `merge-poll-budget-exhausted` in place of `base-advanced-after-arming` and the comment's marker line `livespec-merge-poll-budget-exhausted`. The item MUST NOT be left `active` under a claim whose run has ended.

with

> A pull request the forge then reports OPEN, not in conflict, with auto-merge still armed, and with no check the forge reports as required in a terminal failure is a HANDED-OFF merge wait. Every such check MUST be passing or still running, judged after any automatic re-run the failed-check paragraph below requested. For a handed-off merge wait the Dispatcher MUST NOT rest the item at `blocked` and MUST NOT release its claim. It MUST leave the item `active` under its claim and journal one `merge-wait-handed-off` row naming the run id, the pull request number, its head, the seconds the merge wait spent, and the name of every required check still running. It MUST add one ledger comment to the item that opens with the marker line `livespec-merge-wait-handed-off` and carries the same names and figures. That comment is subject to the same identifier-shape, template-opener and journal-on-failure rules as the `livespec-base-advanced-after-arming` comment above, and a comment that fails them MUST NOT prevent the handoff. The dispatch MUST report exit code 0 under §"Dispatcher exit codes", and no exit code is added or redefined. A handed-off merge wait is completed by §"Stranded claim release". A pull request the forge reports OPEN and not in conflict but with auto-merge no longer armed, or whose required checks cannot be read, MUST rest the item exactly as above, at `blocked` with `blocked_reason: needs-human`, through the same transition, journal row, ledger comment rules and recovery chain, with the named cause `merge-poll-budget-exhausted` in place of `base-advanced-after-arming` and the comment's marker line `livespec-merge-poll-budget-exhausted`. Apart from a handed-off merge wait, the item MUST NOT be left `active` under a claim whose run has ended.

In SPECIFICATION/contracts.md, §"Stranded claim release", in the **Holds.** list, append to item 8 (`run-succeeded`), after its existing text:

> When the item's newest dispatch journaled a `merge-wait-handed-off` row for that run, the pass MUST NOT merely hold the claim. When the forge reports the pull request merged and the preconditions of `reconcile-merged` hold, the Dispatcher MUST perform `reconcile-merged` for the item in the same pass, with no `resolve-blocked` and no `resume`. When the forge reports a required check of the pull request in a terminal failure, the Dispatcher MUST record exactly the outcome the merge wait's terminal required-check failure records. It MUST judge only the attempt the merge wait would judge, so the results of an attempt the merge wait already re-ran are disregarded, and it MUST NOT request a second automatic re-run for a workflow run the merge wait already re-ran. When the forge reports the pull request closed without merging, or OPEN with auto-merge no longer armed, the Dispatcher MUST rest the item at `blocked` with `blocked_reason: needs-human` with the named cause `merge-poll-budget-exhausted`, exactly as the merge wait's own budget-exhausted rest does. When the forge reports the pull request OPEN with auto-merge armed and every required check passing or still running, the claim MUST stay held as `run-succeeded`, and its held entry MUST name `merge-wait-handed-off`. When the forge cannot be read, the claim stays held as this item already states.

In SPECIFICATION/scenarios.md, replace the heading and body of `## Scenario 220 — An exhausted merge-poll budget on an open pull request rests the item for resume` with:

~~~~markdown
## Scenario 220 — An exhausted merge-poll budget hands an armed, passing pull request to reconciliation

```gherkin
Feature: A slow CI run does not turn a healthy armed pull request into a needs-human item
  As an operator whose armed pull request's CI outlasts the merge wait
  I want the item handed to reconciliation rather than rested for a human
  So that a pull request that merges on its own is accepted without resolve-blocked or resume

  Scenario: An armed pull request with passing or running checks is handed off
    Given a run that succeeded and armed auto-merge on its pull request
    And the merge wait's poll budget is exhausted while the forge reports the pull request OPEN, not in conflict, with auto-merge armed
    And every required check is passing or still running
    When the Dispatcher records the outcome
    Then the item stays active under its claim and is not moved to blocked
    And one merge-wait-handed-off journal row names the run id, the pull request, its head, the seconds the wait spent and every required check still running
    And the item carries one ledger comment opening with livespec-merge-wait-handed-off
    And the dispatch exits 0

  Scenario: A handed-off pull request that merges is accepted by the next reconciliation pass
    Given an item whose newest dispatch journaled merge-wait-handed-off
    And the forge now reports its pull request merged
    When the Dispatcher's next stranded-claim reconciliation pass runs
    Then the pass performs reconcile-merged for the item
    And no resolve-blocked and no resume is run for it

  Scenario: A handed-off pull request whose required check fails is routed as a failed check
    Given an item whose newest dispatch journaled merge-wait-handed-off
    And the forge now reports a required check of its pull request in a terminal failure
    When the Dispatcher's next stranded-claim reconciliation pass runs
    Then the outcome is the one the merge wait's terminal required-check failure records

  Scenario: A handed-off pull request closed without merging rests for a human
    Given an item whose newest dispatch journaled merge-wait-handed-off
    And the forge now reports its pull request closed without merging
    When the Dispatcher's next stranded-claim reconciliation pass runs
    Then the item rests at blocked with blocked_reason needs-human and the cause merge-poll-budget-exhausted

  Scenario: An open pull request whose auto-merge is no longer armed rests the item
    Given a run that succeeded and armed auto-merge on its pull request
    And the merge wait's poll budget is exhausted while the forge reports the pull request OPEN and not in conflict with auto-merge no longer armed
    When the Dispatcher records the outcome
    Then the item rests at blocked with blocked_reason needs-human and the cause merge-poll-budget-exhausted
    And the outcome detail names resolve-blocked then resume as the recovery chain

  Scenario: A pull request merged at expiry is not rested
    Given the poll budget is exhausted
    And the forge reports the pull request MERGED on the final read
    When the Dispatcher records the outcome
    Then it proceeds exactly as for a merge observed within the budget
```
~~~~

The retitled heading changes a `## ` heading, so the revise that accepts this proposal MUST update `tests/heading-coverage.json` in the same change: it MUST replace the entry for the old Scenario 220 heading with one for the new heading, keeping the existing test reference only where that test still exercises the new text and otherwise marking it `TODO` with a reason naming bd-ib-bacahf.
