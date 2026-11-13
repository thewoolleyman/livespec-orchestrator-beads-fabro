---
topic: factory-engine-checkpoint-commits-fabro
author: claude-opus-5-5
created_at: 2026-11-13T12:28:48Z
---

## Proposal: publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text says that only `publish_draft`, `pr_refresh` and `pr` publish, and that `publish_draft` pushes exactly the janitor-passed head. It says nothing about which commits that head may carry. Under rebase-merge, a run's engine checkpoint commits (`fabro(<run>): <stage>` subjects) and the janitor's refresh merge commit then land on the default branch as they stand. This proposal adds one paragraph to contracts.md §"Self-contained plugin dispatch", and amends that section's "push exactly the head that `janitor` passed" sentence to admit the folded commit. On a run's first publication, `publish_draft` pushes the janitor-passed head unchanged when every commit beyond the default branch is authored, meaning single-parent with a subject not beginning `fabro(`. Otherwise it pushes one folded commit in its place. That commit sits on the default-branch commit the janitor refreshed onto, has exactly the janitor-passed tree, and carries the full message of the run's latest authored commit. It fails closed with LIVESPEC_PUBLISH_DRAFT_HISTORY_SANITIZE_FAILED when no authored commit exists. Because the tree is unchanged, the janitor's green verdict carries to the push. One scenario exercises it.

### Motivation

Filed as bd-ib-ffw4q3 on legacy-coordinator-agent's R301 decision (2026-11-10 about 20:03Z), under plan publish-draft-green-work-loss (epic bd-ib-acrr56). Its FRESH dispatch on 2026-11-13 was refused at the dispatch stage as spec-change tier, verdict unstated, generalization target "## Self-contained plugin dispatch", linked proposal topic factory-engine-checkpoint-commits-fabro, spec v367. The judgement's rationale: "The visible ratified text says publication happens only in publish_draft, pr_refresh and pr ... It does not say that engine `fabro(<run>): <stage>` checkpoint commits or merge commits are kept out of the pushed head, or that publish_draft folds or refuses them under rebase-merge." A search of SPECIFICATION/contracts.md and scenarios.md on origin/master confirms it. Engine checkpoint commits appear only in `pr_refresh`'s foreign-head carve-out (Scenario 226) and in failed-checkpoint attribution (Scenario 170). Measured: PR #4837 (bd-ib-7cixf3) carried six checkpoint commits and one merge commit beside its one authored commit, and master already carried five `fabro(` subjects in its last 600 commits. Design choices, settled here rather than left open: (a) The folded commit's parent is the merge base, not origin's current tip, because folding onto a later tip with the janitor-passed tree would silently revert that later advance. (b) The message is the LATEST authored commit's full message, trailers included, because its Red-Green trailers describe the final test file content the folded tree holds. A repository whose pre-push replay check still refuses the folded commit fails closed with the hook's output rather than publishing the unfolded history. (c) The rule covers only the first publication. A later push onto an existing published tip is a fast-forward or the refresh-repair lease republish, and folding there would rewrite a published branch outside the cases the spec allows. Old draft #4859 (c2fb31024) implemented a subject-only squash and is superseded by the fresh run this proposal releases. Placement: publish_draft is this orchestrator's workflow realization, so the paragraph belongs in this repository's contracts.md. Fleet scope: every factory-target repository, all rebase-merge. In-flight survey: no open spec PR or pending proposal states this. #5050 (the-engine-s-per-stage, checkpoint deferral under an open merge or rebase) and the pending the-commit-runner-s-authored are compatible and aligned.

### Proposed Changes

Three edits, all in this repository's spec target.

0. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", in the paragraph that begins "**The run refreshes before the janitor, and publish_draft pushes the janitor-passed head.**": replace the sentence "It MUST push exactly the head that `janitor` passed, so that the pre-push gate honours that verdict instead of re-running the aggregate." with "It MUST push exactly the head that `janitor` passed, or, where the next paragraph requires a folded commit, that folded commit, whose tree is exactly the janitor-passed head's tree, so that the pre-push gate honours that verdict instead of re-running the aggregate." Without this edit the two paragraphs would contradict each other.

1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch": insert the following paragraph immediately after the paragraph that begins "**The run refreshes before the janitor, and publish_draft pushes the janitor-passed head.**".

**publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits.** A factory-target repository merges pull requests by rebase-merge, so every commit between the default branch and a pull request's head lands on the default branch as it stands. A run's working branch can carry two kinds of commit that no stage authored: the engine's per-stage checkpoint commits, whose subjects begin `fabro(` (written `fabro(<run>): <stage>`, optionally followed by an outcome in parentheses), and merge commits, such as the janitor's refresh merge of the default branch that the preceding paragraph requires. An AUTHORED commit is a commit in the range below that has exactly one parent and whose subject does not begin `fabro(`. When origin holds no tip for the run's publish branch, `publish_draft` MUST, before it pushes, read the range from the merge base of the janitor-passed head and the default branch's tip as read from origin, exclusive, to the janitor-passed head, inclusive. When every commit in that range is authored, `publish_draft` MUST push the janitor-passed head unchanged. Otherwise it MUST push in its place one FOLDED commit, and MUST then set the run's working branch to that commit, so that every later stage proceeds from the published head. The folded commit's only parent MUST be that merge base, which is the default-branch commit the janitor refreshed onto, never a later default-branch tip, so a default-branch advance after the janitor's refresh is neither folded in nor reverted; integrating it remains `pr_refresh`'s job. Its tree MUST be exactly the janitor-passed head's tree. Its message MUST be the full message, subject, body and trailers included, of the latest authored commit in the range. Because the tree is unchanged, the janitor's green verdict for it carries to the push under `constraints.md` §"Pre-push gate refinements" ("A green aggregate on the exact tree carries to its push"), and the full check aggregate MUST NOT run a second time for that tree. The push MUST run the repository's hooks normally and MUST NOT use `--no-verify`. When a hook refuses the folded commit or its push, `publish_draft` MUST fail closed with that hook's own output, and MUST NOT push the unfolded head instead. When the range holds no authored commit, `publish_draft` MUST NOT push and MUST fail closed with `LIVESPEC_PUBLISH_DRAFT_HISTORY_SANITIZE_FAILED`, naming the run and the range and stating that it found no authored commit whose message it could keep. A `publish_draft` push made while origin already holds a tip for the publish branch, including the republish after a refresh-repair round, is outside this paragraph and keeps its existing behaviour, as do `pr_refresh` and `pr`. Measured 2026-11-10 on PR #4837 (bd-ib-7cixf3): beside its one authored commit ef68c186f, the pull request carried six engine checkpoint commits (`pr_refresh (failure)`, `refresh_repair`, `fix`, `fix_progress_route`, `fix_commit_settle` and `janitor_admission`) and a `Merge commit '57bfd4a2...'`; the default branch then already carried five `fabro(` subjects among its last 600 commits, including 94924cb74 and 9c44a74b4. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

2. `SPECIFICATION/scenarios.md`: append the following scenario after the last numbered scenario. The revise assigns its number and writes that number into both the heading and the closing sentence of the paragraph above.

## Scenario <number assigned at revise> — publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits

```gherkin
Feature: A run's engine checkpoint and merge commits never reach the default branch through publish_draft
  Scenario: Checkpoint and merge commits are folded into one authored commit
    Given a janitor-passed run head whose commits beyond the default branch include engine checkpoint commits with `fabro(<run>): <stage>` subjects, a merge commit of the default branch and an authored commit
    And origin holds no tip for the run's publish branch
    When publish_draft publishes the run
    Then no commit between the default branch and the pushed head has a subject beginning `fabro(` or more than one parent
    And the pushed head's tree equals the janitor-passed head's tree
    And the pushed commit carries the full message of the run's latest authored commit
    And the run's working branch is set to the pushed commit
    And the full check aggregate is not run a second time for that tree

  Scenario: A run whose commits are all authored is pushed unchanged
    Given a janitor-passed run head whose commits beyond the default branch are all authored single-parent commits
    And origin holds no tip for the run's publish branch
    When publish_draft publishes the run
    Then publish_draft pushes the janitor-passed head unchanged

  Scenario: A run with no authored commit fails closed
    Given a janitor-passed run head whose commits beyond the default branch are all engine checkpoint commits or merge commits
    And origin holds no tip for the run's publish branch
    When publish_draft publishes the run
    Then publish_draft pushes nothing
    And it fails closed with LIVESPEC_PUBLISH_DRAFT_HISTORY_SANITIZE_FAILED naming the run and the range

  Scenario: A default-branch advance after the janitor's refresh is neither folded in nor reverted
    Given a janitor-passed run head refreshed onto default-branch commit B that carries engine checkpoint commits
    And the default branch on origin has since advanced beyond B
    When publish_draft folds the run's commits
    Then the folded commit's only parent is B
    And its tree equals the janitor-passed head's tree
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add, in the same change, one `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, `"work_item": "bd-ib-ffw4q3"` and a `reason` that names the owed test's tier as "integration tier or above". It MUST then REGENERATE the debt register with `uv run python -m livespec_dev_tooling.heading_coverage_debt`, and never author its entry by hand.
