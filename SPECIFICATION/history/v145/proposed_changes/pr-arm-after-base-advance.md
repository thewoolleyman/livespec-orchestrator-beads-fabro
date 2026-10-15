---
topic: pr-arm-after-base-advance
author: claude-opus-5-5
created_at: 2026-10-15T16:12:37Z
---

## Proposal: pr routes a rejected arming back to pr_refresh when the default branch has advanced

### Target specification files

- SPECIFICATION/contracts.md

### Summary

When the forge rejects pr's head-bound auto-merge arming, the pull request is still OPEN at the verified head, and the default branch's current tip is not an ancestor of that head, the run returns to pr_refresh instead of failing closed to needs_human. The route goes through a follow-on command node, so every command node keeps two outcomes, and the engine visit limits are required to accommodate it.

### Motivation

Two instances on 2026-10-15. (1) Run 01M4ZVSKDP1V (bd-ib-rv2jk4, PR 3014, dispatcher 0.199.0): pr_refresh, refresh_repair, fix, review, review_fix, proof_capture, proof_verify and publish_draft all succeeded with final head da21c8e3. Then pr marked PR 3014 ready, and `gh pr merge --rebase --auto --match-head-commit da21c8e3` was refused by GitHub with "This branch can't be rebased (mergePullRequest)". The stage failed closed as LIVESPEC_PR_ARM_FAILED to needs_human, because master had advanced between the refresh and the arming (f95ddb3d at 15:18Z, c7040c03 at 15:27Z, release 3a2a826a at 15:38Z). Its diagnostic said the head was not the verified head, but it was. (2) PR 3035 (bd-ib-v4exlm): run 01M4Z5ZJQSZZ succeeded and pr armed auto-merge. A later master commit then conflicted with it in two files, the pull request went DIRTY, and the Dispatcher's merge-poll ended with the generic "PR did not reach MERGED within the poll budget", indistinguishable from slow CI. It was hand-finished. The ratified text absorbs default-branch movement only at pr_refresh. "Scripted publication and proof-head integrity" bounds that to three refreshes per run, which shows the design means to absorb repeated movement inside a run, yet the pr paragraph has no route back to pr_refresh. Movement arriving seconds after the refresh therefore costs a needs_human ending, and movement arriving after the arming costs an unnamed timeout. This proposal absorbs the first shape inside the run. It gives the second shape a named rest and a recovery chain, and it closes the proof-head hole that a resume onto a still-armed pull request would otherwise open.

### Proposed Changes

In SPECIFICATION/contracts.md, the paragraph beginning "`pr` MUST query the exact pull request for the recorded branch", insert after the sentence "A merge hold MUST preserve the ready pull request and leave auto-merge unarmed.":

> When the forge rejects the head-bound auto-merge arming and a re-read reports the pull request OPEN rather than MERGED, `pr` MUST read the pull request's current head, the forge's mergeability report for it, and the authoritative default branch's current tip, read from a fetch of the authoritative branch on origin and never from a local tracking ref, before deciding what the rejection means. When the head is still the head that the latest `verified` or `carried_forward` record of this run names, and the default branch's current tip is not an ancestor of that head (the same test `pr_refresh` applies), `pr` MUST record a refresh-route marker naming this `pr` visit in the run's publication state and exit zero, and the run MUST return to `pr_refresh`. That `pr_refresh` visit refreshes onto an advanced default branch, so it counts toward the three-refresh non-convergence bound of "Scripted publication and proof-head integrity". It MUST NOT consume a refresh-repair round unless the refresh itself takes the refresh-repair route. The refreshed head then takes the decision of "Proof carry-forward across a refresh" exactly as any other changed-head refresh, so only a head named by a `verified` or `carried_forward` record can reach the next arming. When `pr` is entered again on that route, it finds the pull request already out of draft and reports that it readied nothing; that is expected and is not a failure. When the head differs from the recorded head, `pr` MUST fail closed as it does today. When the default branch's tip is an ancestor of the head, or when the forge cannot report the head, the mergeability or the default branch's tip, `pr` MUST fail closed naming the forge's rejection cause or the measurement it could not take. It MUST NOT route to `pr_refresh` on an unobservable answer.

In the paragraph "**The stages.**", add: the command node `pr` MUST be followed by a command node `pr_route` that exits non-zero exactly when `pr` recorded the refresh-route marker for this visit, and zero otherwise. `pr_route` MUST consume the marker on every visit, so a marker left by an earlier `pr` visit can never route a later one. `pr_route`'s failure edge MUST lead to `pr_refresh`, and its unconditional edge MUST lead to the existing successor of `pr`. `pr`'s own failure edge is unchanged. Every command node keeps exactly two outcomes and an unconditional outgoing edge.

After the sentence in "Refresh-repair accounting" that begins "The `fix` node's visit limit MUST accommodate", add: "The visit limits of `pr_refresh`, `pr_refresh_head`, `pr`, `pr_route` and every node on the proof loop MUST accommodate the entries the `pr` → `pr_refresh` route adds beyond the three counted refreshes, so that the ratified non-convergence cause, and not an engine visit cap, ends a run that keeps meeting an advanced default branch."

## Proposal: A rejected arming names the forge's cause instead of asserting a head mismatch

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The stage output for a rejected auto-merge arming names the forge's rejection message, the pull request's state, its mergeability, its head and whether that equals the verified head, and the default branch's tip and whether it is an ancestor of the head. It never asserts a head mismatch that the stage did not measure.

### Motivation

LIVESPEC_PR_ARM_FAILED states "the head it carries is not the head whose proof this run verified" for every rejected arming. In run 01M4ZVSKDP1V the head was the verified head da21c8e3 and the cause was rebaseability, so the diagnostic sent the operator after a head substitution that never happened. See the Motivation of the first proposal in this file.

### Proposed Changes

In SPECIFICATION/contracts.md, the `pr` paragraph, add after the routing text of the preceding proposal:

> Every rejected arming that does not end in `MERGED` MUST write one stage-output line naming the forge's rejection message verbatim, the pull request's state, the forge's mergeability report, the pull request's current head, whether that head equals the head of the latest `verified` or `carried_forward` record of this run, the default branch's current tip, and whether that tip is an ancestor of the head. The line MUST NOT state that the head differs from the verified head unless that comparison was taken and differed.

## Proposal: pr_refresh disarms auto-merge before it refreshes a pull request

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Before pr_refresh rebases onto an advanced default branch, or routes to refresh repair, it disarms any auto-merge request on the run's pull request. A head that no proof record names can therefore never reach the forge's merge queue, and pr re-arms only after fresh proof or a carry-forward.

### Motivation

A head-bound arming binds only the arming call (`--match-head-commit`), not later pushes. A pull request that is still armed when a resumed run's pr_refresh, or the refresh-repair route's fix and publish_draft, pushes a refreshed head would merge on green CI before proof_capture, proof_verify or pr see that head, contradicting "only a proof record naming the new head ... can reach final publication". The specification already has a disarm action (setting a merge hold on an armed item). See the Motivation of the first proposal in this file.

### Proposed Changes

In SPECIFICATION/contracts.md, the paragraph "**Scripted publication and proof-head integrity.**", after "When the default branch has advanced beyond the current base, `pr_refresh` MUST rebase," insert before the rebase:

> Before it rebases, `pr_refresh` MUST read whether the run's pull request carries an auto-merge request and, when it does, MUST disarm it. When the request cannot be read or cannot be disarmed, `pr_refresh` MUST fail closed naming that measurement or action, before any rebase or push. Only `pr` arms auto-merge, and only for a head named by the latest `verified` or `carried_forward` record of this run, so a disarmed pull request stays unarmed until `pr` re-arms it.

## Proposal: An armed pull request made unmergeable by a later default-branch commit rests at needs-human with a named cause

### Target specification files

- SPECIFICATION/contracts.md

### Summary

When the Dispatcher's post-run merge wait twice in a row observes an armed pull request that the forge reports as conflicting with the default branch, the dispatch ends blocked at stage merge-poll with the cause base-advanced-after-arming. The item rests at blocked with blocked_reason needs-human, the dispatch writes the needs-human-blocked row and a marker-line comment and exits 4, and the outcome names the recovery chain: resolve-blocked, then resume, which enters pr_refresh.

### Motivation

PR 3035 sat armed and DIRTY until the merge-poll budget ran out, and the outcome text was identical to a slow-CI timeout. See the Motivation of the first proposal in this file.

### Proposed Changes

In SPECIFICATION/contracts.md, add a paragraph immediately after the `pr` paragraph:

> **Armed pull request overtaken by the default branch.** After a run arms auto-merge, the Dispatcher's merge wait MUST read the forge's mergeability report on each poll. When two consecutive polls report the pull request OPEN and in conflict with the default branch, the wait MUST stop before the poll budget, and the dispatch outcome MUST be `blocked` at stage `merge-poll` with the named cause `base-advanced-after-arming`. The Dispatcher MUST rest the item at `blocked` with `blocked_reason: needs-human`, through the same transition and `needs-human-blocked` journal row that a `needs_human` terminal produces, with the cause as the item's question. The item MUST NOT be left `active`, and the claim MUST NOT be released to `ready`. `blocked_reason` gains no member. The dispatch reports exit code 4 under §"Dispatcher exit codes", and no exit code is added or redefined. Before the blocked transition, the Dispatcher MUST add one ledger comment to the item that opens with the marker line `livespec-base-advanced-after-arming` and carries the run id, the factory name, the pull request number, its head and the default branch's tip. The comment MUST carry names and figures only, every name in it MUST be identifier-shaped as §"Dispatch trace correlation" defines that term, a name that is not identifier-shaped MUST be left out with the comment stating how many were left out, and MUST pass the shared template-opener detector before it is written. A comment that fails the detector, or that cannot be written, MUST be journaled with its reason and MUST NOT prevent the blocked transition. The outcome detail MUST name the recovery chain: `resolve-blocked:<work-item-id>:ready`, then `resume --item <work-item-id>`. The Dispatcher MUST NOT disarm, close or rewrite the pull request itself; the resumed run's `pr_refresh` disarms it before refreshing, as "Scripted publication and proof-head integrity" requires. An exhausted poll budget on a pull request the forge does not report as conflicting keeps its existing outcome. In §"Run account in the valve summary", the sentence "that a `needs_human` termination routed the decision to this valve" MUST read "that a `needs_human` termination, or the Dispatcher-side ending that rested it, routed the decision to this valve".

In §"Resume from a published pull request (`resume --item`)", after the sentence defining the *resumed-at stage*, add: "When the earlier run terminated through `exit` after `pr` armed auto-merge, the resumed-at stage is `pr_refresh`, and the resume record MUST name the factory record as the source that decided it."

## Proposal: Scenario 184: the default branch advances between pr_refresh and the auto-merge arming

### Target specification files

- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Adds Scenario 184, exercising the four paragraphs above. Scenario 182 is reserved by the pending factory-addresses-from-a-gitops-registry proposal, and 183 is ratified in v144.

### Motivation

Behaviour MUST be carried by a scenario, per the template's authoring discipline. See the Motivation of the first proposal in this file.

### Proposed Changes

Append to SPECIFICATION/scenarios.md, and add a matching tests/heading-coverage.json row (test "TODO", with a reason naming the implementation child filed after ratification under plan bd-ib-ku7phe). Each case MUST be exercised by that child's tests before the row leaves TODO:

## Scenario 184 — The default branch advancing between pr_refresh and the arming re-enters pr_refresh, and an armed pull request it overtakes rests at needs-human with a named cause

```gherkin
Feature: Default-branch movement after pr_refresh is absorbed inside the run, and never merges an unproved head
  As the maintainer of a repository dispatched to the factory
  I want default-branch movement that arrives after the refresh handled like movement that arrives before it
  So that a proof-verified run is not ended for a human because master moved a few seconds too late

  Scenario: A refreshable advance before the arming re-enters pr_refresh and then arms
    Given a run whose latest verified record names head H
    And the default branch advances to tip T, which is not an ancestor of H, with a commit that does not conflict with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then pr records the refresh-route marker and pr_route routes the run to pr_refresh, which counts one refresh toward the three-refresh bound and takes no refresh-repair round
    And the refreshed head takes the carry-forward decision before pr is entered again
    And pr reports the pull request already ready and arms auto-merge for the head its latest verified or carried_forward record names

  Scenario: A conflicting advance before the arming re-enters pr_refresh and takes refresh repair
    Given a run whose latest verified record names head H
    And the default branch advances to tip T with a commit that conflicts with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then the run enters pr_refresh, which restores head H and records a refresh-repair brief naming each conflicted path together with the run commit being applied, and routes to fix

  Scenario: A rejected arming with no default-branch advance fails closed naming the forge's cause
    Given a run whose latest verified record names head H, and the default branch's tip is an ancestor of H
    When the forge rejects the head-bound arming
    Then pr fails closed, and its output names the forge's rejection message, the pull request state, its mergeability, that the head equals H, and the default branch's tip
    And the output does not state that the head differs from the verified head

  Scenario: An armed pull request overtaken by a conflicting commit rests at needs-human with a named cause
    Given a run that armed auto-merge for head H and terminated through exit
    And a later default-branch commit conflicts with the pull request
    When two consecutive merge-wait polls report the pull request OPEN and conflicting with the default branch
    Then the dispatch ends blocked at stage merge-poll with the cause base-advanced-after-arming and exit code 4
    And the item rests at blocked with blocked_reason needs-human, with one livespec-base-advanced-after-arming comment and one needs-human-blocked journal row
    And the outcome detail names resolve-blocked for the item and then resume

  Scenario: Resuming an overtaken armed pull request disarms it before refreshing
    Given that item resolved to ready and resumed
    When the resumed run enters pr_refresh at the default branch's advanced tip
    Then pr_refresh disarms the pull request's auto-merge request before it rebases or routes to refresh repair
    And the pull request is armed again only by pr, for a head named by a verified or carried_forward record of the resumed run
```
