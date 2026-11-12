---
topic: a-commit-settle-node-whose
author: claude-opus-5-5
created_at: 2026-11-12T10:51:23Z
---

## Proposal: A commit settle node never passes over a merge or rebase it could not end

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a commit settle node's `git rebase --continue`, `git rebase --abort` or `git merge --abort` does not complete, the node MUST settle the stage as failed, even when the commit run itself passed. It MUST name LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED, the stage, the git command and git's own output in its recorded output and in the re-entry brief. The run MUST re-enter the node's own agent stage (implement, fix or review_fix) with that brief, and MUST NOT route onward while the operation is still in progress. This applies to all three commit settle nodes. When the stage's re-entry budget is spent, the run ends at needs-human naming the unresolved operation.

### Motivation

Today a commit settle node prints LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED to stderr and exits 0 when the continue or abort it runs does not complete. The stage is graded success, its brief still reads passed, and the next node inherits a tree with the rebase or merge still in progress. Measured 2026-11-12 on livespec-dev-tooling-5lhafp, petri run 01M770EZV522AZ4R2A7R29VCHH, released 0.320.0. The agent's `git rebase -i` (a Green amend of a non-HEAD Red commit) had been broken by the engine's per-stage checkpoint commits: update_ref expected d326ba0fb while the branch was at 409c3a40. implement_commit_settle then graded success twice with the rebase left in place (08:53:57Z and 10:19:19Z). janitor@1 failed on 'already a rebase-merge directory', fix_commit_settle failed, and the run spent about 2h25m before ending at its 364-minute wall. A second instance is in the fix stage: on bd-ib-rzkhqv run 01M75FHR657MXCJ0KZ9FX0M1S4, fix_commit_settle graded success with an unresolved `git rebase --continue`. The spec states no rule for what a commit settle node does when ending the operation fails, so the success grade is unconstrained. Routed by legacy-coordinator-agent under its spend duty; work item bd-ib-ebwpxw.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`.** Insert this paragraph immediately AFTER the paragraph that begins **A settled failed commit run is recorded with its cause.** and BEFORE the paragraph that begins **A commit run outlives a node-timeout cut.**:

> **A commit settle node never passes over a merge or rebase it could not end.** This paragraph governs the commit settle nodes that "A commit settle node ends its own wait first." names: `implement_commit_settle`, `fix_commit_settle` and `review_fix_commit_settle`. After a commit settle node has settled the turn's commit run, it ends any merge or rebase that the turn left in progress in the run's working tree. It continues a rebase when the commit run settled passed, and aborts the merge or rebase when the commit run settled failed. When that `git rebase --continue`, `git rebase --abort` or `git merge --abort` exits non-zero, or a merge or rebase is still in progress after it ran, the node MUST settle the stage as failed, even when the commit run itself settled passed. The node's recorded output and the re-entry brief MUST name `LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED`, the stage, the git command that did not complete, the settled commit run's identity and state, and git's own error output for that command. The run MUST then re-enter the node's own agent stage (`implement`, `fix` or `review_fix`) with that brief, spending the same re-entry budget a failed commit run spends in that stage. It MUST NOT route to any stage after it while the operation remains in progress. When that budget is already spent, the run MUST end at the `needs_human` terminal with a cause naming `LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED` and the stage. A continue that stops on a later conflicting pick is one such case, and its brief additionally names the pick and each conflicted path. To clear the state, the node MUST NOT abort or discard a rebase whose commit run settled passed, because the settled commit sits on that rebase's `HEAD`. When the continue or abort completes and no merge or rebase is left in progress, the node's outcome is decided by the settled commit run's state, exactly as before this paragraph. Measured 2026-11-12: on livespec-dev-tooling-5lhafp run 01M770EZV522AZ4R2A7R29VCHH, `implement_commit_settle` graded success twice while `git rebase --continue` had not completed, because engine checkpoint commits had moved the branch past the head the rebase recorded. The next janitor visit failed on the leftover rebase state, and the run ended at its wall about 2h25m later. Scenario 179 in `scenarios.md` exercises this paragraph.

**Edit 2 — `SPECIFICATION/scenarios.md`, §"Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "A re-entered review_fix turn is told why its Green amend failed". The scenario's heading is unchanged.

```gherkin
  Scenario: A settle whose rebase continue does not complete settles the stage failed
    Given an implement-stage agent whose Green amend through the sandbox commit runner was made inside a rebase the turn started
    And that commit run settled passed
    And git rebase --continue exits non-zero because the branch ref has moved past the head the rebase recorded
    When implement_commit_settle runs
    Then the node settles the implement stage as failed
    And its recorded output names LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED, the stage implement, the command git rebase --continue, the commit run and git's own error output
    And the run re-enters implement with a brief naming the same
    And the settled commit is still reachable from the rebase's HEAD

  Scenario: A settle whose abort does not complete settles the stage failed
    Given a fix-stage agent whose commit run settled failed while a merge the turn started is still in progress
    And git merge --abort exits non-zero
    When fix_commit_settle runs
    Then the node settles the fix stage as failed
    And its brief names LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED, the stage fix and the command git merge --abort
    And the run re-enters fix instead of routing to janitor

  Scenario: An unresolved settle whose re-entry budget is spent ends at needs-human naming it
    Given a review_fix stage whose re-entry budget is already spent
    When review_fix_commit_settle settles the stage as failed because a rebase was left unresolved
    Then the run ends at the needs_human terminal
    And the needs-human cause names LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED and the stage review_fix

  Scenario: A settle that ends the operation keeps the commit run's verdict
    Given an implement-stage agent whose Green amend was made inside a rebase the turn started
    And that commit run settled passed
    And git rebase --continue completes with no rebase left in progress
    When implement_commit_settle runs
    Then the node settles the implement stage as passed
    And the settled commit is reachable from HEAD
```
