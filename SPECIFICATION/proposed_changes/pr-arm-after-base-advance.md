---
topic: pr-arm-after-base-advance
author: claude-opus-5-5
created_at: 2026-10-15T16:03:36Z
---

## Proposal: pr routes a rejected arming back to pr_refresh when the default branch has advanced

### Target specification files

- SPECIFICATION/contracts.md

### Summary

When the forge rejects pr's head-bound auto-merge arming, the pull request has not merged, its head is still the verified head, and the default branch has advanced past the base the run's head was refreshed onto, pr routes the run to pr_refresh within the existing three-refresh bound instead of failing closed to needs_human.

### Motivation

Two instances on 2026-10-15. (1) Run 01M4ZVSKDP1V (bd-ib-rv2jk4, PR 3014, dispatcher 0.199.0): pr_refresh, refresh_repair, fix, review, review_fix, proof_capture, proof_verify and publish_draft all succeeded with final head da21c8e3. Then pr marked PR 3014 ready, and `gh pr merge --rebase --auto --match-head-commit da21c8e3` was refused by GitHub with "This branch can't be rebased (mergePullRequest)". The stage failed closed as LIVESPEC_PR_ARM_FAILED to needs_human, because master had advanced between the refresh and the arming (f95ddb3d at 15:18Z, c7040c03 at 15:27Z, release 3a2a826a at 15:38Z). (2) PR 3035 (bd-ib-v4exlm): run 01M4Z5ZJQSZZ succeeded and pr armed auto-merge. A later master commit then conflicted with it in two files, the pull request went DIRTY, and the Dispatcher's merge-poll ended with the generic "PR did not reach MERGED within the poll budget". It was hand-finished. The ratified text absorbs default-branch movement only at pr_refresh: "Scripted publication and proof-head integrity" bounds it to three refreshes per run, which shows the design means to absorb repeated movement inside a run. The pr paragraph, however, has no route back to pr_refresh, so the same movement arriving seconds after the refresh costs a needs_human ending and an operator resume. The operator route that already exists, resume, enters pr_refresh before pr; this proposal moves that route inside the run for the first shape, and names the ending and route for the second.

### Proposed Changes

In SPECIFICATION/contracts.md, the paragraph beginning "`pr` MUST query the exact pull request for the recorded branch", insert after the sentence "A merge hold MUST preserve the ready pull request and leave auto-merge unarmed.":

> When the forge rejects the head-bound auto-merge arming and a re-read reports the pull request still OPEN, `pr` MUST read the pull request's current head, the forge's mergeability report for it, and the default branch's current tip before deciding what the rejection means. When the head is still the head the latest `verified` or `carried_forward` record of this run names, and the default branch's tip is not the base that head was last refreshed onto, `pr` MUST route the run to `pr_refresh` rather than fail closed. That `pr_refresh` visit refreshes onto an advanced default branch and therefore counts toward the three-refresh non-convergence bound of "Scripted publication and proof-head integrity"; it MUST NOT consume a refresh-repair round unless the refresh itself takes the refresh-repair route. The refreshed head then takes the decision of "Proof carry-forward across a refresh" exactly as any other changed-head refresh, so only a head named by a `verified` or `carried_forward` record can reach the next arming. When the head differs from the recorded head, `pr` MUST fail closed as it does today. When the default branch has not advanced past that base, or when the forge cannot report the head, the mergeability or the default branch's tip, `pr` MUST fail closed naming the forge's rejection cause, or the measurement it could not take; it MUST NOT route to `pr_refresh` on an unobservable answer.

In the paragraph "**The stages.**", the command node `pr` MUST carry a conditional edge to `pr_refresh` for this route, in addition to its existing success and failure edges.

## Proposal: A rejected arming names the forge's cause instead of asserting a head mismatch

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The stage output for a rejected auto-merge arming names the forge's rejection message, the pull request's state, its mergeability and whether its head matched the verified head; it no longer asserts that the head differs when the stage did not measure that.

### Motivation

LIVESPEC_PR_ARM_FAILED currently states "the head it carries is not the head whose proof this run verified" for every rejected arming. In run 01M4ZVSKDP1V the head WAS the verified head da21c8e3, and the cause was rebaseability against an advanced master. An operator reading the diagnostic is sent to investigate a head substitution that never happened. Two instances on 2026-10-15. (1) Run 01M4ZVSKDP1V (bd-ib-rv2jk4, PR 3014, dispatcher 0.199.0): pr_refresh, refresh_repair, fix, review, review_fix, proof_capture, proof_verify and publish_draft all succeeded with final head da21c8e3. Then pr marked PR 3014 ready, and `gh pr merge --rebase --auto --match-head-commit da21c8e3` was refused by GitHub with "This branch can't be rebased (mergePullRequest)". The stage failed closed as LIVESPEC_PR_ARM_FAILED to needs_human, because master had advanced between the refresh and the arming (f95ddb3d at 15:18Z, c7040c03 at 15:27Z, release 3a2a826a at 15:38Z). (2) PR 3035 (bd-ib-v4exlm): run 01M4Z5ZJQSZZ succeeded and pr armed auto-merge. A later master commit then conflicted with it in two files, the pull request went DIRTY, and the Dispatcher's merge-poll ended with the generic "PR did not reach MERGED within the poll budget". It was hand-finished. The ratified text absorbs default-branch movement only at pr_refresh: "Scripted publication and proof-head integrity" bounds it to three refreshes per run, which shows the design means to absorb repeated movement inside a run. The pr paragraph, however, has no route back to pr_refresh, so the same movement arriving seconds after the refresh costs a needs_human ending and an operator resume. The operator route that already exists, resume, enters pr_refresh before pr; this proposal moves that route inside the run for the first shape, and names the ending and route for the second.

### Proposed Changes

In SPECIFICATION/contracts.md, the `pr` paragraph, add after the routing text of the preceding proposal:

> Every rejected arming that does not end in `MERGED` MUST write one stage-output line naming the forge's rejection message verbatim, the pull request's state, the forge's mergeability report, the pull request's current head, and whether that head equals the head of the latest `verified` or `carried_forward` record of this run. The line MUST NOT state that the head differs from the verified head unless that comparison was taken and differed.

## Proposal: An armed pull request made unmergeable by a later default-branch commit ends with a named cause

### Target specification files

- SPECIFICATION/contracts.md

### Summary

When the Dispatcher's post-run merge wait observes an armed pull request that the forge reports as conflicting with the default branch, the dispatch ends with the named cause base-advanced-after-arming and names resume as the recovery, instead of exhausting the poll budget and reporting a generic timeout.

### Motivation

PR 3035 sat armed and DIRTY until the merge-poll budget ran out, and the outcome said only "PR did not reach MERGED within the poll budget". That text is identical to a slow-CI timeout, so the ending was triaged as a generic stall and hand-finished. Resume already handles the case correctly, because it enters pr_refresh before pr. Two instances on 2026-10-15. (1) Run 01M4ZVSKDP1V (bd-ib-rv2jk4, PR 3014, dispatcher 0.199.0): pr_refresh, refresh_repair, fix, review, review_fix, proof_capture, proof_verify and publish_draft all succeeded with final head da21c8e3. Then pr marked PR 3014 ready, and `gh pr merge --rebase --auto --match-head-commit da21c8e3` was refused by GitHub with "This branch can't be rebased (mergePullRequest)". The stage failed closed as LIVESPEC_PR_ARM_FAILED to needs_human, because master had advanced between the refresh and the arming (f95ddb3d at 15:18Z, c7040c03 at 15:27Z, release 3a2a826a at 15:38Z). (2) PR 3035 (bd-ib-v4exlm): run 01M4Z5ZJQSZZ succeeded and pr armed auto-merge. A later master commit then conflicted with it in two files, the pull request went DIRTY, and the Dispatcher's merge-poll ended with the generic "PR did not reach MERGED within the poll budget". It was hand-finished. The ratified text absorbs default-branch movement only at pr_refresh: "Scripted publication and proof-head integrity" bounds it to three refreshes per run, which shows the design means to absorb repeated movement inside a run. The pr paragraph, however, has no route back to pr_refresh, so the same movement arriving seconds after the refresh costs a needs_human ending and an operator resume. The operator route that already exists, resume, enters pr_refresh before pr; this proposal moves that route inside the run for the first shape, and names the ending and route for the second.

### Proposed Changes

In SPECIFICATION/contracts.md, add a paragraph immediately after the `pr` paragraph:

> **Armed pull request overtaken by the default branch.** After a run arms auto-merge, the Dispatcher's merge wait MUST read the forge's mergeability report on each poll. When two consecutive polls report the pull request OPEN and in conflict with the default branch, the dispatch MUST end with the named cause `base-advanced-after-arming` rather than continue to the poll budget. The outcome MUST name the pull request, its head, the default branch's tip, and the recovery: resume the item, which enters `pr_refresh` before `pr` under "Resume from an earlier verified head". The Dispatcher MUST NOT disarm, close or rewrite the pull request itself. An exhausted poll budget on a pull request the forge does not report as conflicting keeps its existing outcome.

## Proposal: Scenario 184: the default branch advances between pr_refresh and the auto-merge arming

### Target specification files

- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Adds Scenario 184 exercising the three paragraphs above: a refreshable advance in the pr_refresh-to-arming window re-enters pr_refresh and then arms; a conflicting advance in that window re-enters pr_refresh and takes the refresh-repair route; and an armed pull request later overtaken by a conflicting commit ends with base-advanced-after-arming. Scenario 182 is reserved by the pending factory-addresses-from-a-gitops-registry proposal, and 183 is taken.

### Motivation

Behaviour MUST be carried by a scenario, per the template's authoring discipline. Two instances on 2026-10-15. (1) Run 01M4ZVSKDP1V (bd-ib-rv2jk4, PR 3014, dispatcher 0.199.0): pr_refresh, refresh_repair, fix, review, review_fix, proof_capture, proof_verify and publish_draft all succeeded with final head da21c8e3. Then pr marked PR 3014 ready, and `gh pr merge --rebase --auto --match-head-commit da21c8e3` was refused by GitHub with "This branch can't be rebased (mergePullRequest)". The stage failed closed as LIVESPEC_PR_ARM_FAILED to needs_human, because master had advanced between the refresh and the arming (f95ddb3d at 15:18Z, c7040c03 at 15:27Z, release 3a2a826a at 15:38Z). (2) PR 3035 (bd-ib-v4exlm): run 01M4Z5ZJQSZZ succeeded and pr armed auto-merge. A later master commit then conflicted with it in two files, the pull request went DIRTY, and the Dispatcher's merge-poll ended with the generic "PR did not reach MERGED within the poll budget". It was hand-finished. The ratified text absorbs default-branch movement only at pr_refresh: "Scripted publication and proof-head integrity" bounds it to three refreshes per run, which shows the design means to absorb repeated movement inside a run. The pr paragraph, however, has no route back to pr_refresh, so the same movement arriving seconds after the refresh costs a needs_human ending and an operator resume. The operator route that already exists, resume, enters pr_refresh before pr; this proposal moves that route inside the run for the first shape, and names the ending and route for the second.

### Proposed Changes

Append to SPECIFICATION/scenarios.md, and add a matching tests/heading-coverage.json row (test "TODO", with a reason naming the implementation child filed after ratification under plan bd-ib-ku7phe):

## Scenario 184 — The default branch advancing between pr_refresh and the arming re-enters pr_refresh, and an armed pull request it overtakes ends with a named cause

```gherkin
Feature: Default-branch movement after pr_refresh is absorbed inside the run
  As the maintainer of a repository dispatched to the factory
  I want default-branch movement that arrives after the refresh handled like movement that arrives before it
  So that a proof-verified run is not ended for a human because master moved a few seconds too late

  Scenario: A refreshable advance before the arming re-enters pr_refresh and then arms
    Given a run whose latest verified record names head H, refreshed onto default-branch base B
    And the default branch advances to B2 with a commit that does not conflict with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then pr reads the pull request OPEN at head H and the default branch at B2
    And the run enters pr_refresh, which counts one refresh toward the three-refresh bound
    And the refreshed head takes the carry-forward decision before pr arms auto-merge for the head its record names

  Scenario: A conflicting advance before the arming re-enters pr_refresh and takes refresh repair
    Given a run whose latest verified record names head H, refreshed onto default-branch base B
    And the default branch advances to B2 with a commit that conflicts with the run's commits
    When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
    Then the run enters pr_refresh
    And pr_refresh restores head H, records a refresh-repair brief naming the conflicted paths, and routes to fix

  Scenario: A rejected arming with no default-branch advance fails closed naming the forge's cause
    Given a run whose latest verified record names head H, refreshed onto the current default-branch tip
    When the forge rejects the head-bound arming
    Then pr fails closed and its output names the forge's rejection message, the pull request state, its mergeability and that the head equals H
    And the output does not state that the head differs from the verified head

  Scenario: An armed pull request overtaken by a conflicting commit ends with a named cause
    Given a run that armed auto-merge for head H
    And a later default-branch commit conflicts with the pull request
    When two consecutive merge-wait polls report the pull request OPEN and conflicting with the default branch
    Then the dispatch ends with the cause base-advanced-after-arming naming the pull request, head H, the default branch tip and resume as the recovery
    And the pull request remains armed and unmodified
```

Each scenario MUST be exercised by the implementation child's tests before its coverage row leaves TODO.
