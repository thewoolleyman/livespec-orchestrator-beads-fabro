---
topic: refresh-hook-refusal-routes-to-fix
author: claude-opus-5-5:implement-test-performance
created_at: 2026-11-01T22:40:48Z
---

## Proposal: A refresh commit refused by the commit hook takes refresh repair

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Treat a commit-hook refusal of the commit a refresh itself makes (a merge commit, or a replayed rebase commit) with no conflicted path as a refresh-repair cause: restore the pre-refresh head, record a brief naming the hook's failed targets, and route to fix instead of failing closed to needs_human.

### Motivation

On 2026-11-01 two fully green factory runs ended at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT for exactly this cause. bd-ib-kkuohy (run 01M6BFA19H0J…, orchestrator) and livespec-dev-tooling-hpydsh (run 01M6BQB4JGGN…) each reached publish_draft after proof_capture -> fix and ran the preserve-remote-ancestry `git merge --no-edit origin/master`. The repository's commit hook refused the merge commit: first livespec-dev-tooling-wjqr34's half-pair misroute, then a non-hermetic test (livespec-dev-tooling-dcdgj4) on the suite-green leg. No path conflicted, so publish_draft restored the head and exited without a refresh-repair brief, and refresh_repair routed to needs_human. The current paragraph names only conflicts and a gate rejection at the publishing push. A hook refusal of the refresh's own commit is neither, yet it is the same kind of failure, a repository check refusing the refreshed tree, and the fix node can repair it with hooks running normally. Each such ending currently costs a whole run of finished, verified work plus a human triage. Filed by plan implement-test-performance (livespec-dev-tooling tenant, epic livespec-dev-tooling-sv6m5p).

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph "**Refresh repair.**" (under ## Self-contained plugin dispatch):

1. Replace the opening condition
   "— because the rebase or merge conflicts, or because the refreshed head fails the repository-declared gate that runs before or during the publishing push —"
   with
   "— because the rebase or merge conflicts, because the repository's commit hook refuses a commit the refresh itself makes (the merge commit of a merge refresh, or a commit a rebase replays) while no path is conflicted, or because the refreshed head fails the repository-declared gate that runs before or during the publishing push —".

2. Replace "or each failed gate target." (end of the brief sentence) with
   "or each failed gate target, or, for a commit-hook refusal, each target the hook names as failed together with the last 80 lines of the hook's own output."

3. Replace "only a conflict or a gate rejection takes this route, and every other cause keeps its existing fail-closed behaviour." with
   "only a conflict, a commit-hook refusal of the refresh's own commit, or a gate rejection takes this route, and every other cause keeps its existing fail-closed behaviour. A commit-hook refusal of the refresh's own commit MUST NOT end the run at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT."

In SPECIFICATION/scenarios.md, under ## Scenario 176, add after "Scenario: A refreshed head that fails the gate is restored and repaired":

  Scenario: A refresh commit refused by the commit hook is restored and repaired
    Given a run whose janitor stage succeeded at head H
    And the refresh onto the advanced default branch conflicts on no path
    And the repository's commit hook refuses the commit the refresh makes
    When publish_draft refreshes the run onto the default branch
    Then the run's working branch is reset to H with no merge or rebase in progress
    And a refresh-repair brief names H, the targeted default-branch commit and each target the hook named as failed
    And the run enters the fix node rather than needs_human

No ## heading is added, removed or renamed, so tests/heading-coverage.json is unchanged.
