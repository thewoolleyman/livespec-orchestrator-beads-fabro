---
topic: proof-loop-graph-change
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-20T23:20:00Z
---

## Proposal: Bound the credential freshness requirement by enforced limits, and let a non-overlapping refresh carry a re-proved proof forward

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

This proposal makes two changes, landed as one change to the `implement-work-item` graph's proof loop.

First, the worker's maximum run budget, which the freshness gate requires a projected credential to outlive, becomes the smaller of two enforced figures: the workflow-resolved execution allowance, and a bounded credential-use window equal to a committed credential queue allowance plus the dispatch's resolved whole-run wall budget. The worker's credential-use deadline is measured from projection by that same figure. Today the requirement is the allowance alone, so every loop added to the proof path raises it. That is how the ratified recapture route (v175) pushed the requirement to 906555 s, past the 864000 s a fresh Codex credential carries, and was reverted in v0.229.3.

Second, a `pr_refresh` that applies cleanly and overlaps neither the item's paths nor the proof's observed paths carries the verified proof forward even when the incoming paths are not inert, once the run has already re-proved after one changed-head refresh. Today every such refresh re-proves, so runs chase an advancing default branch.

### Motivation

- Coordinator R342 (stop-the-line, 2026-10-20) and R344: v0.229.2 refused every Codex-mode dispatch at the freshness gate. The revert restored 844275 s and brought back the proof-loop defect of `bd-ib-j56cur`. `bd-ib-2oxr6v` re-lands the recapture route and needs this definition to fit.
- The whole-run wall budget (`dispatcher.run_wall_budget_seconds`, default 21600 s, enforced by the progress watchdog) and the in-sandbox credential-use guard, which kills the agent at an absolute deadline, are both ratified and enforced. With them, a requirement of the allowance alone is no longer the tightest one the factory can stand behind.
- Prior art: `bd-ib-yx7pdm` (closed; maintainer-approved 2026-10-05) defined the requirement as the workflow-resolved allowance plus the margin, before the wall budget existed. This proposal revisits that definition on the later evidence and is offered for ratification for that reason.
- The refresh rule is coordinator R344(i). Master protection is `strict=false` with only `ci-green` required, so re-proving on every base advance is stricter than the merge gate. Runs measured chasing master: `t3znvw` about 200 minutes, `davaxq` 125 minutes.
- Measurements and the design comparison: `plan/fabro-currency/research/013-credential-requirement-and-refresh-carry-forward-2026-10-20.md`.

### Proposed Changes

**1.** In SPECIFICATION/contracts.md, section "Worker credential projection", insert after the paragraph that begins "The Dispatcher MUST NOT dispatch a worker unless every projected credential covered by the **freshness gate**" the following paragraph:

> The worker's maximum run budget is the smaller of two figures. The first is the execution allowance the Dispatcher derives from the resolved workflow graph. The second is the bounded credential-use window, which is the resolved `dispatcher.credential_queue_allowance_seconds` plus the whole-run wall budget resolved for the same dispatch (§"ACP node timeouts", "Whole-run wall budget key"). The worker's credential-use deadline MUST be the projection instant plus that same figure, and the in-sandbox guard MUST stop coding-agent execution at that deadline, so the host gate and the in-sandbox guard use one figure. The freshness gate MUST require that figure plus the documented margin. The bound on credential use is the guard deadline, not the progress watchdog. The whole-run wall budget is not itself a hard bound: queue time is excluded from it, a held or unmeasured budget lets a run continue past it, and it is enforced only while the watchdog polls. A run first launched within the credential queue allowance is never stopped by the deadline before the whole-run wall budget's worth of running time has elapsed. At the run's first coding-agent launch, the in-sandbox start check MUST refuse the launch when the time remaining before the credential-use deadline is less than the resolved whole-run wall budget, naming the deadline, the remaining time and the budget. This is the queue-exceeded refusal. It is a different measurement from the start check's comparison of the credential's remaining life against the freshness requirement, and both MUST be made. A run that queued past the credential queue allowance is therefore refused before any coding-agent turn starts, and is never stopped by the guard in the middle of a turn on its queue's account. `dispatcher.credential_queue_allowance_seconds` is a committed-only positive integer of seconds, default **86400**. A non-positive or non-integer value MUST be rejected before any run exists, naming the key. Its resolution and journaling follow the whole-run wall budget key. The status and manual-renewal surfaces MUST report the same figure and name which of the two figures governed. For a dispatch in flight they MUST also report the queue time consumed against the credential queue allowance. Scenario 228 in `scenarios.md` exercises this paragraph.

> **A run ended by its credential-use deadline.** When the in-sandbox guard stops a coding agent at the credential-use deadline in the middle of a node, or refuses an agent launch because the deadline has passed, the Dispatcher MUST end the run under the export-then-terminate precondition of §"A factory run never awaits a human". It exports the run's record and writes and reads back the preserve-by-reference pointer, which names the run's published pull request and publish branch head when they exist, before the run is ended. It MUST journal exactly one `credential-use-deadline-reached` record carrying the run id, the factory, the node, the projection instant, the credential-use deadline, the queue time consumed, the governing figure, the preserve-by-reference pointer, and the cause. The cause is `queue-exceeded` for the start check's queue-exceeded refusal, `launch-refused` for a later agent launch refused because the deadline has passed, and `killed-mid-node` for an agent stopped at the deadline. The same disposition applies to all three. It MUST rest the item at `blocked` with `blocked_reason` `needs-human`, with a ledger comment naming the run, the node, the deadline, the cause and the pointer. The record anchors resume under §"Resume from a published pull request (`resume --item`)" exactly as a `run-wall-budget-exceeded` record does. Such an ending MUST NOT be reported as a plain failed run, MUST NOT be left without a journal record, and MUST NOT count toward any non-convergence or rework bound. Scenario 228 in `scenarios.md` exercises this paragraph.

**2.** In SPECIFICATION/contracts.md, section containing "**Proof carry-forward across a refresh.**", paragraph "**The decision.**", replace the clause "every incoming path is beneath an inert class;" with:

> every incoming path is beneath an inert class, or this run has already re-proved after one changed-head `pr_refresh` and the verified record is that re-proof's own record;

and add at the end of that paragraph:

> A run re-proves after a changed-head `pr_refresh` at most once on the second condition's account. A refresh whose incoming paths overlap the item paths or the observation scope, or whose rebase conflicts in any path that is not a declared record file, MUST still take the re-proof or refresh-repair route this section already requires. A `carried_forward` record written under the second condition MUST say that the incoming paths were not all inert and that the run's one re-proof covered them. Scenario 229 in `scenarios.md` exercises these sentences.

**3.** In SPECIFICATION/scenarios.md, Scenario 178, the case "An incoming change outside the inert classes re-proves" MUST gain the Given step "And the run has not yet re-proved after a changed-head refresh", so that it remains true under change 2.

**4.** In SPECIFICATION/scenarios.md, add at the end of the file (tests/heading-coverage.json MUST gain an entry for each in the same revise):

## Scenario 228 — The credential freshness requirement is the smaller of the execution allowance and the bounded credential-use window

```gherkin
Feature: A proof-loop edge cannot price a fresh credential out of dispatch
  As an operator of a factory that routes nodes to Codex
  I want the freshness requirement bounded by limits the factory enforces
  So that a ratified graph change does not refuse every Codex dispatch

  Scenario: The bounded window governs when it is smaller
    Given the resolved workflow's execution allowance is 902955 seconds
    And dispatcher.credential_queue_allowance_seconds resolves to 86400 and the whole-run wall budget to 21600
    When codex-cred-status reports the requirement
    Then the required lifetime is 111600 seconds, naming the bounded credential-use window as the governing figure
    And a credential with 864000 seconds of remaining life passes the freshness gate and the dispatch creates a run

  Scenario: The worker deadline uses the same figure
    Given a dispatch whose governing figure is 108000 seconds
    When the credential is projected at instant P
    Then the worker's credential-use deadline is P plus 108000 seconds
    And a coding agent still running at that deadline is stopped

  Scenario: A long queue is refused at agent launch and rests for resume
    Given a dispatch whose credential queue allowance is 86400 seconds and whose whole-run wall budget is 21600 seconds
    And the run is first launched more than 108000 seconds after projection
    When the first coding-agent node launches
    Then the launch is refused naming the credential-use deadline
    And the dispatch journal carries one credential-use-deadline-reached record with cause queue-exceeded
    And the item rests at blocked with blocked_reason needs-human

  Scenario: A queue between the allowance and the deadline is refused before any turn starts
    Given a dispatch whose credential queue allowance is 86400 seconds and whose whole-run wall budget is 21600 seconds, projected at instant P
    And the run's first coding-agent launch is at P plus 90000 seconds, so 18000 seconds remain before the deadline
    When the start check runs
    Then it refuses the launch because 18000 seconds is less than the 21600-second budget, naming the deadline, the remaining time and the budget
    And no coding-agent turn starts, so no agent is stopped in the middle of a turn
    And the dispatch journal carries one credential-use-deadline-reached record with cause queue-exceeded
    And the item rests at blocked with blocked_reason needs-human

  Scenario: A run whose wall budget is held past it ends at the guard deadline with its work preserved
    Given a dispatch whose governing figure is 108000 seconds, projected at instant P
    And the run has published a draft pull request with head H
    And the run's whole-run wall budget is unmeasured, so the watchdog does not cancel it
    When a coding agent is still running at P plus 108000 seconds
    Then the guard stops the agent at that deadline
    And the Dispatcher exports the run's record and reads back a preserve-by-reference pointer naming the pull request and head H before the run ends
    And the dispatch journal carries one credential-use-deadline-reached record with cause killed-mid-node naming the node, the deadline, the queue time consumed and the pointer
    And the item rests at blocked with blocked_reason needs-human, and resume --item is anchored on that record
    And the ending is not reported as a plain failed run and is not counted toward any non-convergence bound

  Scenario: The status surface shows queue time consumed
    Given a dispatch in flight whose credential queue allowance is 86400 seconds
    And its first agent launched 3600 seconds after projection
    When codex-cred-status is read
    Then it reports 3600 seconds of queue time consumed against the 86400-second allowance
```

## Scenario 229 — A non-overlapping refresh after one re-proof carries the proof forward

```gherkin
Feature: A run stops chasing an advancing default branch once it has re-proved
  As the maintainer of a repository dispatched to the factory
  I want a re-proved run to keep its proof across a clean refresh that cannot touch what it proved
  So that a run is not sent round capture, review and replay for every base advance

  Scenario: A second clean refresh with non-inert, non-overlapping paths carries forward
    Given a run that re-proved after one changed-head pr_refresh, with verified record R on head V
    And the default branch advanced again with a commit that changes a Python module that is neither an item path nor in R's observation scope
    When pr_refresh rebases the branch cleanly, the gate passes and the leased push yields head N with an unchanged patch identity
    Then the pull request carries one carried_forward record naming V and N that says the incoming paths were not all inert and that the run's one re-proof covered them
    And the run proceeds from pr_refresh to pr without visiting proof_capture

  Scenario: An overlapping refresh still re-proves
    Given a run that re-proved after one changed-head pr_refresh
    And the default branch advanced with a commit that changes a path in the verified record's observation scope
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the pull request carries one reproof_required record naming that path
    And the run enters proof_capture for head N
```
