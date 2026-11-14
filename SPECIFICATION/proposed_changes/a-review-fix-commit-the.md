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

contracts.md's paragraph "A fix turn grades each tree once, through its commit hook" already requires a successful review_fix turn to leave a head whose last commit in that turn passed its commit hook's gate. It states a routing remedy only for an OPEN RED settled passed: re-enter the stage, or end at needs_human at the visit limit. It does not say what happens when review_fix_commit_settle settles the turn's last commit run as FAILED. This proposal adds that case. The run re-enters review_fix with a brief naming the failed commit run and the hook's failing target. An engine checkpoint commit MUST NOT carry the failed run's staged changes onto the run branch. At the visit limit the run ends at needs_human naming the failed run. Scenario 199 gains two scenarios.

### Motivation

Measured on factory run 01M7BR72AW0RJMBX5ZBR7A9G8H (bd-ib-3lxeqf, petri, 2026-11-14). review_fix@2 committed a behaviour-preserving refactor through the sandbox commit runner (commit-32773f6c9fdc418589ec38b7e810a446). The hook refused it after 2515.77 s at check-commit-pairs-source-and-test. review_fix_commit_settle@2 settled that run failed and exited 0. The engine checkpoint for that node then committed the staged product .py as e99febd65, with no TDD trailers. review_fix_open_red_route saw no open Red and routed to janitor_admission. janitor@3 failed check-red-green-replay on e99febd65; fix@1 correctly refused to rewrite the checkpoint; the run ended needs-human and the item needed a seeded relaunch from a pre-checkpoint wip ref. Linked work-item: bd-ib-kcetlr. The dispatch-time spec-change tier screen held it (verdict partial, generalization target Scenario 199, linked topic a-review-fix-commit-the): the ratified scenarios state re-entry only for an open Red settled passed, and do not state re-entry for a failed commit run with no open Red, nor that the engine checkpoint must not carry a failed commit's staged changes. The fix stage is deliberately out of scope: it has its own completion gate and progress node, and this proposal does not change its handling.

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph beginning "**A fix turn grades each tree once, through its commit hook.**", immediately after the sentence "When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at `needs_human` with a cause naming the open Red commit.", insert:

> A `review_fix` turn whose last commit run `review_fix_commit_settle` settles `failed` has not met this obligation either: the commit hook refused that commit, so no passing hook run graded the turn's tree. When `review_fix_commit_settle` settles the turn's last commit run `failed`, the run MUST re-enter `review_fix` instead of routing to `janitor_admission`. The re-entered turn's brief MUST name the failed commit run and the commit hook's failing target. An engine checkpoint commit MUST NOT carry the staged changes of a failed commit run onto the run's branch; those changes MUST remain available to the re-entered `review_fix` turn in its working tree. When the `review_fix` stage's visit limit is reached while its last commit run is still settled `failed`, the run MUST end at `needs_human` with a cause naming the failed commit run and the commit hook's failing target, and the run's tree MUST be preserved. This sentence group governs `review_fix` only; a `fix` turn keeps its existing completion-gate handling.

The paragraph's opening scope sentence ("This paragraph governs a `fix` turn or a `review_fix` turn that completes successfully and routes to `janitor`...") is unchanged: a review_fix turn whose commit run failed is exactly a turn that would otherwise have routed to janitor.

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 199 — A fix turn grades each tree once, through its commit hook", immediately after the scenario "An open Red at the stage's visit limit ends at needs_human naming it", append these two scenarios. They add no H2 heading, so tests/heading-coverage.json is unchanged:

```gherkin
  Scenario: A review_fix commit run settled failed re-enters review_fix with the hook's refusal
    Given a review_fix turn whose last commit run the commit hook refused
    And review_fix_commit_settle settles that commit run failed
    When the run leaves the commit-settle node
    Then the run re-enters review_fix instead of janitor_admission
    And the re-entered turn's brief names the failed commit run and the commit hook's failing target
    And no engine checkpoint commit carries that failed commit run's staged changes onto the run's branch

  Scenario: A failed review_fix commit run at the visit limit ends at needs_human naming it
    Given the review_fix stage's visit limit is reached
    And its last commit run is still settled failed
    When the run leaves the stage
    Then the run ends at needs_human with a cause naming the failed commit run and the commit hook's failing target
    And the run's tree is preserved
```
