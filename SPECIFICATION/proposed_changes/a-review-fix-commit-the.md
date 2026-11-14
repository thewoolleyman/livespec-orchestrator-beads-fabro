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

contracts.md's paragraph "A fix turn grades each tree once, through its commit hook" already requires a successful review_fix turn to leave a head whose last commit in that turn passed its commit hook's gate. It states a routing remedy only for an OPEN RED settled passed. It says nothing about the case where review_fix_commit_settle settles the turn's last commit run as FAILED. This proposal adds that case.

- The run re-enters review_fix with the failed run's recorded cause, under a failed-commit-run budget of its own, as fix_commit_settle already has.
- After the failed verdict, the workflow sets that run's staged changes aside in the git directory, so no later engine checkpoint can carry them onto the run branch before the re-entered turn commits. This needs no engine change.
- When either bound is spent, the run ends at needs_human naming the failed runs. The preserved tree includes the set-aside changes.
- An open Red, a no-verdict run and a still-running run are each covered.

Scenario 199 gains three scenarios.

### Motivation

Measured on factory run 01M7BR72AW0RJMBX5ZBR7A9G8H (bd-ib-3lxeqf, petri, 2026-11-14). review_fix@2 committed a behaviour-preserving refactor through the sandbox commit runner (commit-32773f6c9fdc418589ec38b7e810a446). The hook refused it after 2515.77 s at check-commit-pairs-source-and-test. review_fix_commit_settle@2 settled that run failed and exited 0. The engine checkpoint for that node then committed the staged product .py as e99febd65, with no TDD trailers. review_fix_open_red_route saw no open Red and routed to janitor_admission. janitor@3 failed check-red-green-replay on e99febd65; fix@1 correctly refused to rewrite the checkpoint; the run ended needs-human and the item needed a seeded relaunch from a pre-checkpoint wip ref. Linked work-item: bd-ib-kcetlr. The dispatch-time spec-change tier screen held it (verdict partial, generalization target Scenario 199, linked topic a-review-fix-commit-the): the ratified scenarios state re-entry only for an open Red settled passed, and do not state re-entry for a failed commit run with no open Red, nor that the engine checkpoint must not carry a failed commit's staged changes.

Graded PASS-WITH-FIXES by legacy-coordinator-agent (a7764b59). This revision answers both blocking points.

(B1) Engine checkpoints run for FAILED nodes too: the run's needs-human branch carries `fabro(...): fix (failure)` and `fabro(...): janitor (failure)` checkpoint commits. So a node's exit status cannot keep staged changes out of a checkpoint. The guarantee is therefore placed in the workflow: the settle node sets the changes aside before it ends, and the observable is named. It is independent of #5050, which defers checkpoints only while a merge or rebase is open.

(B2) The budget is a counter of its own, mirroring `fix_commit_settle`'s `livespec-fix-failed-commit-runs` (three failed runs, then `LIVESPEC_FIX_COMMIT_RUN_FAILED_EXHAUSTED` at needs_human). It is separate from the open-Red count. Each re-entry also spends one of review_fix's `max_visits`, so both bounds apply, and the cause names the one that was reached.

### Proposed Changes

**Edit 1: SPECIFICATION/contracts.md.** In the paragraph beginning "**A fix turn grades each tree once, through its commit hook.**", immediately after the sentence "When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at `needs_human` with a cause naming the open Red commit.", insert:

> A `review_fix` turn whose last commit run `review_fix_commit_settle` settles `failed` has not met this obligation either, because the commit hook or Git refused that commit and no passing hook run graded the turn's tree. A commit run that settles `no-verdict` made no commit and is treated here exactly as a `failed` one. When the settle's bounded wait ends with the commit run still `running`, the settle MUST first stop that commit run, which makes it `no-verdict`.
>
> When `review_fix_commit_settle` settles the turn's last commit run `failed`, the run MUST re-enter `review_fix` instead of routing to `janitor_admission`. The re-entry brief MUST carry what §"A settled failed commit run is recorded with its cause" requires the settle to record for that run: the failed target names, or the literal `failed targets: none`, Git's refusal line when the hook passed and Git then refused the commit, and the run's final output lines. For a `no-verdict` run, the brief MUST say that the run made no commit and name its state.
>
> Before `review_fix_commit_settle` ends after settling a commit run `failed`, the workflow MUST set aside every change that commit run had staged, together with any other uncommitted change in the run's working tree. They are held in the run's git directory, outside the run branch's tracked tree; a stash is sufficient. The set-aside changes MUST be restored into the working tree at the start of the re-entered `review_fix` turn, and the re-entry brief MUST say that they were restored. Observable: no engine checkpoint commit written from `review_fix_commit_settle`'s own checkpoint up to the re-entered `review_fix` turn's first commit run changes any path the failed commit run had staged. A checkpoint written while that commit run was still in flight is governed by §"A commit leg completes past one tool call" and the settle node's existing head restore, not by this sentence.
>
> Failed `review_fix` commit runs MUST be counted on a counter of their own, separate from the open-Red count; a commit run settled twice counts once. The budget is three failed commit runs, as for `fix_commit_settle`. A re-entry also spends one `review_fix` visit. When the third failed commit run is settled, or a re-entry would exceed the `review_fix` stage's visit limit, the run MUST end at `needs_human` instead of re-entering. The needs-human cause MUST name which bound was reached, every counted failed commit run's identity, and each run's failed target names, or `failed targets: none`. Before that ending's preservation, the set-aside changes MUST be restored into the working tree, so the tree that §"A factory run never awaits a human" preserves includes them.
>
> When the turn's last commit is also an open Red, for example a Green amend that the hook refused, the open-Red rules above govern the route and the brief. That brief carries the failed run's cause as §"A settled failed commit run is recorded with its cause" already requires, and the failed run still counts against this budget. An open-Red needs-human cause at the visit limit MUST also name that failed run.
>
> This sentence group governs `review_fix` only.

**Edit 2: SPECIFICATION/scenarios.md.** Inside the gherkin block of "## Scenario 199 — A fix turn grades each tree once, through its commit hook", immediately after the scenario "An open Red at the stage's visit limit ends at needs_human naming it", append the three scenarios below. They add no H2 heading, so tests/heading-coverage.json is unchanged.

```gherkin
  Scenario: A review_fix commit run settled failed re-enters review_fix with its recorded cause and its changes set aside
    Given a review_fix turn whose last commit run the commit hook refused
    And review_fix_commit_settle settles that commit run failed
    When the run leaves the commit-settle node
    Then the run re-enters review_fix instead of janitor_admission
    And the re-entry brief carries the failed target names or "failed targets: none" and the run's final output lines
    And no engine checkpoint commit before the re-entered turn's first commit run changes a path that failed run had staged
    And the re-entered turn starts with those changes restored to its working tree

  Scenario: A review_fix commit run that ends without a verdict is treated as failed
    Given a review_fix turn whose last commit run settles no-verdict, or is still running when the settle's bounded wait ends
    When the run leaves the commit-settle node
    Then a still-running commit run has been stopped and counts as no-verdict
    And the run re-enters review_fix with a brief saying the commit run made no commit

  Scenario: An exhausted review_fix failed-commit budget ends at needs_human with the changes preserved
    Given review_fix_commit_settle settles a third failed commit run for the run, or a re-entry would exceed the review_fix visit limit
    When the run leaves the commit-settle node
    Then the run ends at needs_human with a cause naming the bound reached, each counted failed commit run and its failed target names
    And the preserved tree includes the changes the failed commit run had staged
```
