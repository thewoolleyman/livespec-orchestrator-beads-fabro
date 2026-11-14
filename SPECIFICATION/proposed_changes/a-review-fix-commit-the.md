---
topic: a-review-fix-commit-the
author: claude-opus-5-5
created_at: 2026-11-14T07:01:36Z
---

## Proposal: A review_fix commit run settled failed re-enters review_fix with the hook's refusal, and no engine checkpoint carries its staged changes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md's paragraph "A fix turn grades each tree once, through its commit hook" already requires a successful review_fix turn to leave a head whose last commit in that turn passed its commit hook's gate. It states a routing remedy only for an OPEN RED settled passed. It says nothing about the case where review_fix_commit_settle settles the turn's last commit run as FAILED. This proposal adds that case for BOTH stages that commit through the runner, `fix` and `review_fix`.

- The run re-enters the same stage with the failed run's recorded cause, under a failed-commit-run budget of three per stage. fix_commit_settle already implements that budget; review_fix gains it.
- After the failed verdict, the workflow sets that run's staged changes aside in the git directory, so no engine checkpoint before the re-entered review_fix node's own checkpoint can carry them. A re-entered turn that starts no commit run ends at needs_human, never at the janitor. This needs no engine change.
- When either bound is spent, the run ends at needs_human naming the failed runs. EVERY preserving ending restores the set-aside changes first.
- An open Red, a no-verdict run and a still-running run are each covered.

Scenario 199 gains five scenarios.

### Motivation

Measured on factory run 01M7BR72AW0RJMBX5ZBR7A9G8H (bd-ib-3lxeqf, petri, 2026-11-14). review_fix@2 committed a behaviour-preserving refactor through the sandbox commit runner (commit-32773f6c9fdc418589ec38b7e810a446). The hook refused it after 2515.77 s at check-commit-pairs-source-and-test. review_fix_commit_settle@2 settled that run failed and exited 0. The engine checkpoint for that node then committed the staged product .py as e99febd65, with no TDD trailers. review_fix_open_red_route saw no open Red and routed to janitor_admission. janitor@3 failed check-red-green-replay on e99febd65; fix@1 correctly refused to rewrite the checkpoint; the run ended needs-human and the item needed a seeded relaunch from a pre-checkpoint wip ref. Linked work-item: bd-ib-kcetlr. The dispatch-time spec-change tier screen held it (verdict partial, generalization target Scenario 199, linked topic a-review-fix-commit-the): the ratified scenarios state re-entry only for an open Red settled passed, and do not state re-entry for a failed commit run with no open Red, nor that the engine checkpoint must not carry a failed commit's staged changes.

Graded PASS-WITH-FIXES by legacy-coordinator-agent (a7764b59). This revision answers both blocking points.

(B1) Engine checkpoints run for FAILED nodes too: the run's needs-human branch carries `fabro(...): fix (failure)` and `fabro(...): janitor (failure)` checkpoint commits. So a node's exit status cannot keep staged changes out of a checkpoint. The guarantee is therefore placed in the workflow: the settle node sets the changes aside before it ends, and the observable is named. It is independent of #5050, which defers checkpoints only while a merge or rebase is open.

(B2) The budget is a counter of its own, mirroring `fix_commit_settle`'s `livespec-fix-failed-commit-runs` (three failed runs, then `LIVESPEC_FIX_COMMIT_RUN_FAILED_EXHAUSTED` at needs_human). It is separate from the open-Red count. Each re-entry also spends one of review_fix's `max_visits`, so both bounds apply, and the cause names the one that was reached.

### Proposed Changes

**Edit 1: SPECIFICATION/contracts.md.** In the paragraph beginning "**A fix turn grades each tree once, through its commit hook.**", immediately after the sentence "When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at `needs_human` with a cause naming the open Red commit.", insert:

> A `fix` or `review_fix` turn whose last commit run its commit-settle node (`fix_commit_settle` or `review_fix_commit_settle`) settles `failed` has not met this obligation either, because the commit hook or Git refused that commit and no passing hook run graded the turn's tree. A commit run that settles `no-verdict` made no commit and is treated here exactly as a `failed` one. When the settle's bounded wait ends with the commit run still `running`, the settle MUST first stop that commit run, which makes it `no-verdict`.
>
> When the commit-settle node settles the turn's last commit run `failed`, the run MUST re-enter that same stage, `fix` or `review_fix`, instead of routing to `janitor_admission`. The re-entry brief MUST carry what §"A settled failed commit run is recorded with its cause" requires the settle to record for that run: the failed target names, or the literal `failed targets: none`, Git's refusal line when the hook passed and Git then refused the commit, and the run's final output lines. For a `no-verdict` run, the brief MUST say that the run made no commit and name its state.
>
> Before the commit-settle node ends after settling a commit run `failed`, the workflow MUST set aside every change that commit run had staged, together with every other uncommitted change in the run's working tree, untracked files included. They are held in the run's git directory, outside the run branch's tracked tree; a stash taken with untracked files included is sufficient. The set-aside changes MUST be restored INSIDE the re-entered stage's node, before its turn makes any other change, so no checkpoint written on the re-entry path ahead of that node can carry them, the open-Red route node's included. The re-entry brief MUST say that they were restored and MUST direct the turn to commit its tree through the commit runner before it ends.
>
> Observable: no engine checkpoint commit written after the commit-settle node settles the failed commit run, up to but not including the re-entered stage node's own checkpoint, changes any path the failed commit run had staged. This includes the settle node's own checkpoint, which the engine writes even when that node ends failed. A checkpoint written while that commit run was still in flight is governed by §"A commit leg completes past one tool call" and the settle node's existing head restore, not by this sentence.
>
> The re-entered stage node's own checkpoint can still carry the restored changes when its turn ends without starting a commit run, and no workflow node runs before that checkpoint. So when a `fix` or `review_fix` turn re-entered under this rule ends without starting any commit run, the next commit-settle visit MUST route the run to `needs_human`, not to `janitor_admission` and not into another re-entry. Its needs-human cause MUST name the failed commit run the re-entry answered and state that the re-entered turn made no commit.
>
> Each stage's failed commit runs MUST be counted on a counter of that stage's own, separate from the open-Red count; a commit run settled twice counts once. The budget is three failed commit runs per stage. A re-entry also spends one visit of that stage. When a stage's third failed commit run is settled, or a re-entry would exceed that stage's visit limit, the run MUST end at `needs_human` instead of re-entering. The needs-human cause MUST name every bound that was reached, every counted failed commit run's identity, and each run's failed target names, or `failed targets: none`.
>
> When the turn's last commit is also an open Red, for example a Green amend that the hook refused, the open-Red rules above govern the route and the brief. That brief carries the failed run's cause as §"A settled failed commit run is recorded with its cause" already requires, and the failed run still counts against this budget. An open-Red needs-human cause at the visit limit MUST also name that failed run.
>
> On EVERY ending that preserves the run's tree under §"A factory run never awaits a human" while changes are set aside under this rule, the set-aside changes MUST be restored into the working tree before that preservation, so the preserved tree includes them. This covers an exhausted failed-commit budget, an open Red at the visit limit, a re-entered turn that made no commit, a node timeout, and every other ending of that kind.

**Edit 2: SPECIFICATION/scenarios.md.** Inside the gherkin block of "## Scenario 199 — A fix turn grades each tree once, through its commit hook", immediately after the scenario "An open Red at the stage's visit limit ends at needs_human naming it", append the five scenarios below. They add no H2 heading, so tests/heading-coverage.json is unchanged.

```gherkin
  Scenario: A fix or review_fix commit run settled failed re-enters its stage with its recorded cause and its changes set aside
    Given a fix or review_fix turn whose last commit run the commit hook refused
    And that stage's commit-settle node settles that commit run failed
    And neither that stage's failed-commit-run budget nor its visit limit is spent
    When the run leaves the commit-settle node
    Then the run re-enters that same stage instead of janitor_admission
    And the re-entry brief carries the failed target names or "failed targets: none" and the run's final output lines
    And no engine checkpoint commit before the re-entered stage node's own checkpoint changes a path that failed run had staged, the settle node's own failure checkpoint included
    And the re-entered stage node restores those changes to its working tree before its turn makes any other change

  Scenario: A fix or review_fix commit run that ends without a verdict is treated as failed
    Given a fix or review_fix turn whose last commit run settles no-verdict, or is still running when the settle's bounded wait ends
    And neither that stage's failed-commit-run budget nor its visit limit is spent
    When the run leaves the commit-settle node
    Then a still-running commit run has been stopped and counts as no-verdict
    And the run re-enters that same stage with a brief saying the commit run made no commit

  Scenario: An exhausted failed-commit budget ends at needs_human with the changes preserved
    Given a fix or review_fix commit-settle node settles that stage's third failed commit run, or a re-entry would exceed that stage's visit limit
    When the run leaves the commit-settle node
    Then the run ends at needs_human with a cause naming every bound reached, each counted failed commit run and its failed target names
    And the preserved tree includes the changes the failed commit run had staged

  Scenario: A re-entered fix or review_fix turn that starts no commit run ends at needs_human
    Given a fix or review_fix turn re-entered after a failed commit run
    And that turn ends without starting any commit run
    When the run reaches that stage's commit-settle node
    Then the run ends at needs_human instead of janitor_admission or another re-entry
    And the cause names the failed commit run the re-entry answered and states the re-entered turn made no commit
    And the preserved tree includes the set-aside changes

  Scenario: An open Red at the visit limit with changes set aside preserves them
    Given a fix or review_fix stage whose visit limit is reached with its last commit still an open Red
    And changes are set aside after a failed commit run
    When the run ends at needs_human
    Then the set-aside changes are restored into the working tree before preservation
    And the needs-human cause also names the failed commit run
```

Re-check 2 (legacy-coordinator-agent 3e750bae). Restoration before preservation now covers every preserving ending, not only the budget-exhausted one. Scope is widened to `fix`. No measured immunity exists: `fix_commit_settle` exits 1 on a failed run, and the engine checkpoints failed nodes, measured here as `fix (failure)` and `janitor (failure)` on run 01M7BR72AW0R's needs-human branch. So `fix` gets the same set-aside, the same restore and the same no-commit rule; its existing three-run budget (`livespec-fix-failed-commit-runs`) is what this states. bd-ib-kcetlr's Definition of Done covers `review_fix` only; the `fix` half is routed as its own item when this proposal is revised in.
