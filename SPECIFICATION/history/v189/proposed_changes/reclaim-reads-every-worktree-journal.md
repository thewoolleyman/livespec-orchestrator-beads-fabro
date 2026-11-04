---
topic: reclaim-reads-every-worktree-journal
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:42:51Z
---

## Proposal: The publish-branch reclaim finds an earlier dispatch journaled in any worktree of the repository

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Stale publish-branch reclaim before a re-dispatch" acts only for an item with an earlier dispatch, and defines that as a record in THIS checkout's dispatch journal. A dispatch journaled only in another checkout "is invisible here". A re-dispatch launched from a secondary worktree, such as the coordinator's canary worktree, of an item first dispatched from the primary therefore skips the reclaim, and `publish_draft` refuses on the surviving branch. This proposal widens the definition to the dispatch journals of every worktree of the same repository, meaning every checkout sharing its git common directory. The reclaim's holds and its one-question-per-first-dispatch boundary are unchanged.

### Motivation

Work-item bd-ib-ewdqub, measured 2026-10-16: run 01M51PPR6VVT (bd-ib-tixpma), dispatched from ~/.worktrees/livespec-orchestrator-beads-fabro/canary-hp-candidate, failed at publish_draft@1 because origin/feat/bd-ib-tixpma carried a prior run's head b367ed3e and draft PR 2869 from a 2026-10-13 dispatch journaled in the primary checkout. The reclaim that exists for exactly this case did not run. Plan spec-implementation-lockstep R1 batch 6 routes it here as an amendment of the reclaim's own scope sentence.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Stale publish-branch reclaim before a re-dispatch", bullet "**Only a re-dispatch asks.**", replace "An *earlier dispatch* of an item is a record in THIS checkout's dispatch journal that names a run id or a declared dispatch id for the item;" and "a dispatch journaled only in another checkout's journal is invisible here, in which case the reclaim does not run and `publish_draft` refuses exactly as it did before the reclaim existed." so that the bullet reads:

> An *earlier dispatch* of an item is a record that names a run id or a declared dispatch id for the item in the dispatch journal of ANY worktree of this repository, meaning every checkout that shares its git common directory; a dry-run plan and a pre-run refusal are not earlier dispatches. A dispatch journaled only on another host is invisible here, in which case the reclaim does not run and `publish_draft` refuses exactly as it did before the reclaim existed. A worktree journal that cannot be read MUST be journaled as `publish-branch-reclaim-held` with the new reason `journal-unobservable`, naming the path, rather than read as no earlier dispatch. Scenario 225 in `scenarios.md` exercises this bullet.

Leave the rest of the bullet (from "For an item with no earlier dispatch the Dispatcher MUST NOT") unchanged.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 225 — The publish-branch reclaim finds an earlier dispatch journaled in another worktree

```gherkin
Feature: A re-dispatch from a secondary worktree reclaims the surviving branch
  As an operator re-dispatching from a canary worktree
  I want the reclaim to see a dispatch journaled in the primary checkout
  So that publish_draft does not refuse on a branch the reclaim exists to clear

  Scenario: An earlier dispatch in the primary is found from a worktree
    Given an item whose earlier dispatch is journaled only in the repository's primary checkout
    And its publish branch survives on origin with no live run
    When the item is re-dispatched from a secondary worktree of the same repository
    Then the reclaim preserves the branch to a run-scoped ref and deletes it from origin

  Scenario: An unreadable worktree journal holds
    Given a worktree of the repository whose dispatch journal cannot be read
    When the reclaim looks for an earlier dispatch
    Then it journals publish-branch-reclaim-held with reason journal-unobservable naming that path
```

