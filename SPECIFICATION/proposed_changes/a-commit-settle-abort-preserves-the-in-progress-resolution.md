---
topic: a-commit-settle-abort-preserves-the-in-progress-resolution
author: claude-opus-5-5
created_at: 2026-11-11T21:44:53Z
---

## Proposal: A commit-settle abort preserves the in-progress integration it discards

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a commit-settle step settles a failed commit run while the turn's merge or rebase is still in progress, it MUST record the working tree (every resolved and conflicted path) as one commit off the operation's HEAD and push it to a new resolution ref, refs/livespec/resolution/<work-item-id>/<run-id>/<n>, before it aborts the operation. It MUST then name that ref in the next turn's re-entry brief, and the re-entered turn MUST restore the resolution instead of redoing it. Resolution refs are not work-in-progress captures, so recovery routing never seeds from them. They follow the work-in-progress push and retention rules.

### Motivation

Today every current design discards the conflict resolution an agent turn did inside a merge or rebase, whenever its commit run fails. The shared commit-settle abort restores the head the operation began from. Work-in-progress captures (Scenario 317) and the needs-human ref preserve only that committed head. Measured 2026-11-11 on bd-ib-pgbr52 run 01M75ZC7R0K9: fix@2 saw the failure cause in its brief and repaired the integration mid-rebase (decomposing the dispatcher under the 250-LLOC gate and fixing an installer pipefail fault). The settle's abort threw that repair away, and fix@3 re-resolved the identical conflict from scratch until the fix budget ran out. The same aborted-integration ending struck b7l6it, e3vbbo, pof4aa and ebdvbn that day. This is the deferral frwp-defer-aborted-resolution-2026-11-11 of plan factory-run-work-preservation (epic bd-ib-nckst7). Plan assertion 5 counts work lost beyond the node visit in progress, and a discarded resolution is the previous visit's work. legacy-coordinator-agent ruled it be filed as a propose-change before assertion 5's seven-day window; pgbr52 brought it forward as a measured non-convergence cost.

### Proposed Changes

Three edits to `SPECIFICATION/contracts.md` and one to `SPECIFICATION/scenarios.md`. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance".** Insert a new paragraph immediately AFTER the paragraph that begins **Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref.** and BEFORE the paragraph that begins **A run's ending names its latest preserved capture on the item.**:

> **A commit-settle abort preserves the integration it discards.** A run's *resolution refs* are the refs `refs/livespec/resolution/<work-item-id>/<run-id>/<n>`, where `<n>` is a decimal ordinal starting at 1. A *commit-settle step* is a command step that waits out and settles an agent stage's commit runs: in the single-implement graph, `implement_commit_settle`, `fix_commit_settle` and `review_fix_commit_settle`. When a commit-settle step settles a commit run as failed while a merge or rebase that the turn started is still in progress, and is about to abort that operation, it MUST first record the operation's in-progress state as one commit and preserve it, and only then abort. The commit's tree MUST be the tree of the working tree as it stands, including every path the turn resolved and every path still marked conflicted, with untracked files that the repository does not ignore included. The commit MUST NOT be made on any branch: it MUST be created with the operation's current `HEAD` as its first parent, so that creating it moves no ref, and it MUST NOT change `HEAD`, the index, the working tree or the operation's own state before the abort runs. This capture is the only commit a preserving step creates, and it is created only in this case; the preceding paragraph's rule that the work-in-progress push MUST NOT create a commit governs that push and is unchanged. Its message MUST name the run id, the step, the operation (`rebase` or `merge`), the commit the operation was applying or merging, the commit it was integrating onto, each path still marked conflicted, and the failed commit run's id. The step MUST push that commit to the run's next resolution ref, numbered one above the highest existing one, under the same push rules the preserving steps above follow: created once and never updated, deleted or force-written while its item is open, hooks disabled, repository-controlled git configuration ignored, and Dispatcher-materialized tooling outside the run's working tree. It MUST then name the ref and the commit in the re-entry brief that the next turn of the same stage reads, beside the failed commit run's cause. A capture or push that fails MUST NOT change the step's outcome or stop the abort, and MUST be reported in the step's own recorded output naming the ref, the commit and the reason. A resolution ref is a recovery artifact for the run's next agent turn. It is NOT a work-in-progress ref: it is not the run's latest preserved capture, the recovery routing of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" MUST NOT rank it or seed from it, no pull request is opened from it, and no publication stage reads it. When the re-entry brief names a resolution ref and the re-entered turn restarts the same operation onto the same commit, the turn's prompt MUST direct it to restore each path the capture holds resolved from that commit, so the earlier resolution is reused rather than redone, and then to apply the fix the re-entry brief's failure cause names. A path that the restarted operation does not conflict on, or that the default branch has changed since the capture, MUST be resolved on its merits, never restored blindly. Measured 2026-11-11: on bd-ib-pgbr52 run 01M75ZC7R0K9, fix@2 repaired a failed refresh integration mid-rebase (it decomposed the dispatcher under the 250-LLOC gate and fixed an installer pipefail fault). `fix_commit_settle` then aborted the rebase after the commit run failed, and fix@3 re-resolved the identical conflict from scratch. The same aborted-integration shape ended b7l6it, e3vbbo, pof4aa and ebdvbn the same day. Scenario 317 in `scenarios.md` exercises this paragraph.

**Edit 2 — `contracts.md`, the paragraph **Publication is mechanically confined to the scripted publication stages.**.** In the sentence "its preservation MUST push only the run's own `refs/heads/needs-human/<run-id>` ref or the run's own work-in-progress refs", replace "or the run's own work-in-progress refs" with ", the run's own work-in-progress refs, or the run's own resolution refs (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "A commit-settle abort preserves the integration it discards")". Every other sentence of that paragraph is unchanged.

**Edit 3 — `contracts.md`, the paragraph **Preservation refs are deleted when the Dispatcher closes or collects an item's runs.**.** The Dispatcher MUST delete the item's resolution refs wherever it deletes the item's work-in-progress refs. In the first deletion sentence, replace "every ref under `refs/livespec/wip/<work-item-id>/` and `refs/livespec/preserved-publish/<work-item-id>/`" with "every ref under `refs/livespec/wip/<work-item-id>/`, `refs/livespec/resolution/<work-item-id>/` and `refs/livespec/preserved-publish/<work-item-id>/`". In the ended-run sentence, replace "it MUST delete that run's work-in-progress refs," with "it MUST delete that run's work-in-progress refs and resolution refs,". Every other sentence is unchanged.

**Edit 4 — `scenarios.md`, §"Scenario 317 — Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after "a committing step without preservation fails the check". The scenario's heading and its governing-clause line are unchanged; the governing-clause line SHOULD additionally name "A commit-settle abort preserves the integration it discards":

```gherkin
  Scenario: a settle abort first preserves the in-progress resolution
    Given a run of work item W whose fix turn rebased onto the default branch, resolved path P in the conflict at commit C, and committed through the detached commit runner
    And that commit run failed while the rebase is still in progress at HEAD R
    When fix_commit_settle settles the commit run as failed
    Then origin's ref refs/livespec/resolution/W/<run-id>/1 points at a commit whose first parent is R and whose tree holds P as the turn resolved it
    And that commit's message names the run, the step, the rebase, commit C, the onto commit and the failed commit run
    And only after that push does the step abort the rebase
    And the re-entry brief for the next fix turn names that ref and commit beside the failed commit run's cause

  Scenario: a resolution ref is never a recovery seed
    Given a run of work item W whose only refs on origin are refs/livespec/wip/W/<run-id>/1 at commit I and refs/livespec/resolution/W/<run-id>/1
    When a re-dispatch of W is graded by recovery routing
    Then the run's latest preserved capture is refs/livespec/wip/W/<run-id>/1
    And recovery routing neither ranks nor seeds from the resolution ref

  Scenario: a re-entered turn restores the preserved resolution instead of redoing it
    Given the re-entry brief names refs/livespec/resolution/W/<run-id>/1, which holds path P resolved for the rebase of commit C onto commit O
    And the default branch has not changed path P since O
    When the re-entered fix turn restarts the same rebase and conflicts on P at commit C
    Then the turn restores P from the resolution commit rather than resolving P again
    And the turn then applies the fix that the re-entry brief's failure cause names

  Scenario: a failed resolution push does not stop the abort
    Given the forge refuses the push of the run's next resolution ref
    When fix_commit_settle settles a failed commit run with a rebase in progress
    Then the step still aborts the rebase and keeps its own outcome
    And the step's recorded output names the ref, the commit and the failure
```

