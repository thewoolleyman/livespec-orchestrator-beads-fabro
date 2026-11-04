---
topic: landed-publication-is-finished-at-publish
author: claude-opus-5-5
created_at: 2026-10-26T23:43:38Z
---

## Proposal: A publication that already landed is finished at publish_draft, not a failure

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Sibling to v226: publish_draft (after its refresh, before pushing or opening a pull request, and again when creation is refused for no commits) takes the merged-reconcile ending when a pull request attributed to a dispatch of the item merged into the default branch with its merge commit in the tip, and the run's head adds no change; every other case and every other stage keeps its existing behaviour.

### Motivation

Routed by petri-factory-on-gmktec on coordinator gitops-fleet-capacity-monitoring's request, spec-first for work-item bd-ib-weje2m (v226's implementer). v226 ("A pull request merged before its refresh") made a merged publication a finished one, but only in pr_refresh. A third instance of the same class failed at publish_draft, which v226 does not reach: on bd-ib-svm3fe run 01M5X2C5FJKSQW84SFG81E6885 the item's fix had already merged as pull request 3731 (from an earlier run's preserved work, 22:30:05Z) and its branch was deleted; at about 22:5xZ the run's publish_draft passed the full pre-push gate (92 of 93 targets, 835 s), pushed the branch anew, then failed on gh pr create with "GraphQL: No commits between master and feat/bd-ib-svm3fe", emitted LIVESPEC_PUBLISH_DRAFT_CREATE_FAILED, refresh_repair reported LIVESPEC_REFRESH_REPAIR_ABSENT, and the run went to needs_human with no question asked. reconcile-merged then closed the item into acceptance. A sibling paragraph is added rather than generalizing v226's, because pr_refresh's detection (its publish branch found absent) differs from these stages' (an empty diff beside a merged pull request); the ending, recording and proof rules are v226's by reference. Both conditions are required, so neither an unrelated merged pull request nor an empty run alone is read as a landed publication.
A first read-only Codex review raised three blockers, folded in: the landed check requires a pull request the Dispatcher attributes to a dispatch of this item, merged into the default branch with its merge commit in the tip (a branch name alone is not enough); and the clause is scoped to publish_draft, leaving refresh_repair and pr_refresh's post-push failure classifications (and the pending rejected-push proposal) untouched.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch" → "### Definition-of-Done and Proof-of-Done stages", after the paragraph "**A pull request merged before its refresh.**", insert immediately after the text

```
runs ended at `needs_human` for work that had landed. Scenario 248 in
`scenarios.md` exercises this paragraph.
```

the following new paragraph (separated by one blank line):

```
**A publication that already landed is finished at publish_draft.** `publish_draft`, after its refresh and before it pushes or opens a pull request, MUST check whether the item's publication has already landed, and MUST make the same check before it fails when the forge refuses pull-request creation because the branch has no commits beyond the default branch. It has landed when all of these hold. First, the forge reports a pull request as MERGED with a non-null merge commit. Second, the Dispatcher attributes that pull request to a dispatch of this item, an earlier dispatch included, because the item's dispatch records name it; a matching branch name alone does not establish that. Third, its base is the default branch, and its merge commit is contained in the default branch's tip as read from origin at the check. Fourth, the run's head adds no change to that tip, that is, its diff against the tip is empty. When it has landed, the publication is finished: `publish_draft` MUST NOT push, open a pull request or route to repair, and the run MUST take the merged-reconcile ending of the preceding paragraph, with that paragraph's recording and its rule that the ending writes no `verified` or `carried_forward` record. The acceptance pass then judges the merged head by the proof evidence leg, so a record of an earlier dispatch of the item that is bound or matched to the item and applies to the merged head counts. In every other case `publish_draft` keeps its existing behaviour. These include a run whose head adds a change to that tip, a run with no attributed merged pull request, a merged pull request into another base, and a state the check cannot read. This paragraph changes no other stage. Measured 2026-10-26 on bd-ib-svm3fe run 01M5X2C5FJKSQW84SFG81E6885: the item's change had merged at 22:30:05Z as pull request 3731 from an earlier run's preserved work, and the forge had deleted its branch. The run's `publish_draft` passed the full pre-push gate in 835 seconds, pushed the branch anew, and then failed on pull-request creation with "No commits between master and feat/bd-ib-svm3fe". `refresh_repair` then found no repair brief, and the run ended at `needs_human` with no question asked, for work already on the default branch. Scenario 256 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 256 — A publication that already landed is finished at publish_draft, not a failure

```gherkin
Feature: publish_draft tells a landed publication from a failure
  Scenario: publish_draft finds the item's change already merged
    Given a run whose head adds no change to the default branch's tip
    And an earlier dispatch of the item has a pull request that the forge reports MERGED into the default branch with merge commit M contained in the tip
    When publish_draft finishes its refresh
    Then publish_draft does not push or open a pull request
    And the run takes the merged-reconcile ending and records the pull request, merge commit M and the merged head

  Scenario: A refused pull-request creation is checked before it fails
    Given a publish_draft that pushed the run's publish branch
    And the forge refuses pull-request creation because the branch has no commits beyond the default branch
    And an earlier dispatch of the item has a MERGED pull request whose merge commit is contained in the default branch's tip
    When publish_draft handles the refusal
    Then the run takes the merged-reconcile ending instead of failing

  Scenario: A run that adds a change has not landed
    Given a run whose head adds a change to the default branch's tip
    And an earlier dispatch of the item has a MERGED pull request
    When publish_draft finishes its refresh
    Then publish_draft pushes and opens a pull request as before

  Scenario: A reused branch name does not make a publication landed
    Given a run whose head adds no change to the default branch's tip
    And a MERGED pull request on the same branch name that no dispatch of this item produced
    When publish_draft finishes its refresh
    Then publish_draft keeps its existing behaviour and does not take the merged-reconcile ending

  Scenario: A merge into another base does not make a publication landed
    Given a run whose head adds no change to the default branch's tip
    And a pull request of an earlier dispatch of the item MERGED into a branch other than the default branch
    When publish_draft finishes its refresh
    Then publish_draft keeps its existing behaviour and does not take the merged-reconcile ending
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-weje2m.
