---
topic: pr-refresh-merged-publication
author: claude-opus-5-5
created_at: 2026-10-26T16:09:26Z
---

## Proposal: pr_refresh treats a pull request merged mid-run with its branch deleted as a finished publication

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

When pr_refresh finds the run's own publish branch absent on origin and the run's pull request MERGED with a non-null merge commit, it takes a merged-reconcile ending, recording the merged head and whether it equals the run's proven head, instead of failing closed as an unobservable remote; every other missing or unobservable remote, and any foreign or changed publish head, stays fail-closed.

### Motivation

Work-item bd-ib-hu67v5 (plan bd-ib-ku7phe, filed 2026-10-16 under coordinator routing R31) is the spec arc for this change, routed here by coordinator gitops-fleet-capacity-monitoring ruling R35. The ratified paragraph says a missing remote MUST fail closed, and a publish branch the forge deleted after merging is a missing remote, so ending such runs at needs_human is today's ratified behaviour. Instance 1: run 01M51D4RYHCB (cited in workflow.fabro's pr_refresh comments) failed LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE because its pull request had auto-merged and its branch was deleted. Instance 2: overseer-q156 run 01M5W2YHVAMB on petri, 2026-10-26: PR 2633 auto-merged at 15:51:25Z, the forge deleted feat/overseer-q156, and pr_refresh failed with "couldn't find remote ref" / ORIGIN_UNOBSERVABLE and went to needs_human for work that had landed; reconcile-merged recovered it by hand. `pr` already treats an already-merged pull request as a recorded success; pr_refresh is the one publication stage that does not.

Open design question from the item, answered here: a stale arming can merge a head before its proof is verified (instance 1's merge preceded proof_verify). The merge cannot be undone, so the run still takes the merged-reconcile ending, but the ending records whether the merged head equals the head the latest verified or carried_forward record names, and never writes a proof record for the merged head, so the existing acceptance proof leg judges an unproven merged head only from proof records that already name it.

This proposal edits a different sentence of the same paragraph than the pending proposal pr-refresh-rejected-push-that-landed-on-origin (the leased-push rejection), and the two compose.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, paragraph "Scripted publication and proof-head integrity", replace the sentence

```
A missing or unobservable remote, or a foreign or
unexpectedly changed publish head, MUST fail closed with a named cause and
recovery artifact pointer.
```

with

```
Except as the next paragraph provides for a pull request
that has already merged, a missing or unobservable remote, or a foreign or
unexpectedly changed publish head, MUST fail closed with a named cause and
recovery artifact pointer.
```

2. Insert a new paragraph immediately after that paragraph's first block (after the sentence ending "recognized idempotently from durable run provenance and matching remote state."):

```
**A pull request merged before its refresh.** When `pr_refresh` finds the run's
own publish branch absent on origin, it MUST read the run's pull request before
it decides the remote is missing. When the forge reports that pull request
MERGED with a non-null merge commit, the publication is finished, and
`pr_refresh` MUST take the merged-reconcile ending instead of failing closed.
On that ending `pr_refresh` MUST NOT fetch-and-rebase, push, disarm, re-prove or
re-arm, and the run MUST end successfully without entering `pr`, so the
Dispatcher observes the merge, runs the post-merge janitor and enters acceptance
exactly as it does for a merge its merge wait observed. The ending MUST record,
in the run's publication state and in the dispatch outcome detail, the pull
request number, the merge commit, the pull request's merged head, the head named
by the latest `verified` or `carried_forward` record of this run or that no such
record exists, and whether those two heads are equal. The ending MUST NOT write
a `verified` or `carried_forward` record for the merged head; when an arming
merged a head that no such record of this run names, the acceptance pass judges
that head only from proof records that already name it. When the publish branch
is absent and the pull request is not MERGED, the forge reports a null merge
commit, or the pull request's state cannot be read, `pr_refresh` MUST fail closed
as an unobservable remote with a named cause and recovery artifact pointer. A
foreign or unexpectedly changed publish head MUST fail closed whatever the pull
request's state. Measured on run 01M51D4RYHCB, and again on run 01M5W2YHVAMB on
2026-10-26 after pull request 2633 auto-merged at 15:51:25Z and the forge
deleted its branch, `pr_refresh` failed closed on the deleted branch, and both
runs ended at `needs_human` for work that had landed. Scenario 248 in
`scenarios.md` exercises this paragraph.
```

3. In `SPECIFICATION/scenarios.md`, append Scenario 248:

````
## Scenario 248 — A pull request merged before its refresh ends the run as a finished publication

```gherkin
Feature: pr_refresh tells a merged publication from a missing remote
  Scenario: A pull request merged mid-run with its branch deleted takes the merged-reconcile ending
    Given a run whose latest verified record names head V
    And an earlier arming merged the run's pull request at head V with merge commit M
    And the forge deleted the run's publish branch
    When pr_refresh queries the publish branch on origin
    Then pr_refresh reads the pull request as MERGED with merge commit M
    And the run takes the merged-reconcile ending without entering pr
    And the ending records the pull request, merge commit M, merged head V, the verified head V and that the two heads are equal
    And the Dispatcher runs the post-merge janitor and enters acceptance
  Scenario: A merged head the run never proved is recorded as unproven
    Given a run whose latest verified record names head V
    And an arming merged the run's pull request at head U before any record named U
    And the forge deleted the run's publish branch
    When pr_refresh queries the publish branch on origin
    Then the run takes the merged-reconcile ending
    And the ending records merged head U, the verified head V and that the two heads differ
    And the ending writes no verified or carried_forward record for head U
  Scenario: A missing branch whose pull request is not merged still fails closed
    Given a run whose publish branch is absent on origin
    And the forge reports the run's pull request OPEN
    When pr_refresh queries the publish branch on origin
    Then pr_refresh fails closed as an unobservable remote with a named cause and recovery artifact pointer
    And the run does not take the merged-reconcile ending
```
````

4. In `tests/heading-coverage.json` add a TODO row for the new Scenario 248 heading, and in `tests/heading-coverage-debt.json` a matching debt row, both owned by plan epic bd-ib-ku7phe until its implementing child is filed after ratification.
