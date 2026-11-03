---
topic: a-plain-re-dispatch-of
author: claude-opus-5-5
created_at: 2026-11-03T04:15:54Z
---

## Proposal: Release for recovery any item whose latest run published, however that run ended

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen the recovery-release condition of "Recovery from the failed run's preserved work". An item whose latest dispatch's run published a head to its publish branch, and which has since returned to ready, is released for recovery however that run ended: an engine failure such as workflow_error, or a succeeded run whose pull request did not merge. Recovery routing then resumes or seeds it from the published work instead of routing it fresh and reclaiming the branch.

### Motivation

Measured 2026-11-03 on bd-ib-yuwftp (livespec-orchestrator-beads-fabro):
- Run 01M6F3KPK1Q7 published draft PR #4225 (feat/bd-ib-yuwftp @ 8b613ab0) after three review rounds. It then ended `failed` / `workflow_error` at 03:16:46Z, because review@4 asked for a fix after the disposition node's visit bound was spent; bd-ib-k7zfog covers that ending. The run reached neither the needs_human nor the non_converged terminal.
- A human valve (`resolve-blocked:bd-ib-yuwftp:ready`) returned the item to ready. The owner's recorded decision was to repair from the published work.
- Under the current text the item was not released for recovery, so it was routed `fresh` without any remote measurement. The plain dispatch ran the stale publish-branch reclaim (8b613ab0 preserved at refs/livespec/preserved-publish/bd-ib-yuwftp/8b613ab0…, branch deleted) and launched run 01M6FSG9B9FY from the default branch (base_sha ba9941a05).
- Three review rounds of finished work were dropped with no error and no record naming the loss as a recovery decision. The run had to be cancelled by hand and resumed.

The same gap covers livespec-dev-tooling-z5fwwn. Its run 01M6F5AZNB4W ended `succeeded` with PR #3203 open; the PR's check-per-file-coverage then went red and the item rested blocked/needs-human. A plain dispatch after the human valve would have reclaimed PR #3203 and restarted from the default branch.

The clause already has the machinery that keeps this work (resume, seeded, held), and every other release route feeds it. The only thing missing is the release condition: an ending that published but reached neither named terminal falls through to `fresh`. Widening the release condition keeps recovery routing as the single routing authority, so no second, launcher-side or ticketing-side rule is needed. The alternative, refusing a plain dispatch of such an item and naming `resume --item`, was rejected: it adds a second authority and leaves the seeded fallback unreachable when resume is inapplicable.

Root-fix work item: bd-ib-yatzb5 (filed under plan implement-test-performance, epic livespec-dev-tooling-sv6m5p, routed by legacy-coordinator-agent). It is held at the spec-change tier for this topic.

### Proposed Changes

Two edits. Every other sentence of the edited paragraph is unchanged.

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".**

Replace the sentence

> An item is also released for recovery when its latest journaled dispatch ended at the workflow's `needs_human` terminal or at a `non_converged` terminal, the item has since returned to `ready` by any path (a human valve, a groom, or a return from `backlog`), and no newer dispatch has been submitted for it.

with

> An item is also released for recovery when its latest journaled dispatch ended at the workflow's `needs_human` terminal or at a `non_converged` terminal, or ended by any other route after that dispatch's run published a head to the item's publish branch, the item has since returned to `ready` by any path (a human valve, a groom, or a return from `backlog`), and no newer dispatch has been submitted for it. *Any other route* includes an engine-level run failure that reaches neither terminal, such as `workflow_error`, and a `succeeded` run whose pull request was left unmerged when the item rested, for example on a red pull-request check. Whether the run published is read from the dispatch's own journal and the forge, and a measurement that cannot be taken is the `held` outcome of routing, never `fresh`.

The sentences that follow it ("For such an item, the pre-claim refusal of §\"Across-dispatch required-result progress\" MUST be graded BEFORE recovery routing ..." through "... the needs-human or non-convergence cause recorded on the item.") now apply to every item that sentence releases, with no change to their text. The routing outcomes (`resume`, `seeded`, `fresh`, `held`), the preserved-work preference order, the rule that the stale publish-branch reclaim runs for `fresh` and `seeded` items only and after the seed's preservation is verified, and the sentence "An item not released for recovery is routed `fresh` without any remote measurement." are all unchanged.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch`.**

Append these two scenarios at the end of the existing gherkin fence. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: A human-valve release after a published run that ended in an engine failure is routed from its published work
    Given an item whose latest dispatch's run published head H to the item's publish branch and then ended failed with workflow_error, reaching neither the needs_human nor the non_converged terminal
    And a human valve has returned the item to ready and no newer dispatch has been submitted for it
    When the Dispatcher next dispatches the item
    Then the item is graded by recovery routing before admission
    And it is routed resume when every resume precondition passes, and otherwise seeded with H or H's preserved-publish ref as its recorded seed commit
    And its run does not start from the default branch
    And the publish branch is reclaimed only after that preservation is verified, and never for a resume route

  Scenario: A rested item whose succeeded run's pull request did not merge is routed from that pull request
    Given an item whose latest dispatch's run ended succeeded with an open pull request at head H that was left unmerged when the item rested
    And the item has since returned to ready and no newer dispatch has been submitted for it
    When the Dispatcher next dispatches the item
    Then the item is graded by recovery routing before admission
    And it is not routed fresh while H is readable on origin
```

