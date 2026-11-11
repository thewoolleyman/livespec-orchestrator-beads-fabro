---
topic: the-preserved-tree-comment-names-the-needs-human-ref
author: claude-opus-5-5
created_at: 2026-11-11T09:33:40Z
---

## Proposal: The preserved-tree comment names the run's needs-human or preservation ref with its merge-base diff size

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The livespec-preserved-tree ledger comment of §"Dispatcher admission, WIP cap, and post-merge acceptance" → "A run's ending names its latest preserved capture on the item" names only the run's work-in-progress refs. When a run ends at needs_human, its tree is preserved on a needs-human ref (or, for a failed engine checkpoint, a preservation ref) that the comment does not mention, so the comment says "the run has no work-in-progress ref" while the work is safely on origin. The comment MUST also name each needs-human ref or failed-checkpoint preservation ref published at the same run's ending, with its tip commit and the size of its diff against its merge-base with the default branch, and MUST NOT state only that the run has no work-in-progress ref when such a ref exists.

### Motivation

Three misreadings on 2026-11-11, each of which treated preserved work as lost.

1. bd-ib-6szexa, run 01M74HXDG6X2. The comment said the run had no work-in-progress ref. refs/heads/needs-human/d462da591e8d4d6286c2ba4be839e344 at 64e4747e8 was on origin, with 7 files and +336/-9 against its merge-base outside .fabro. The dispatching seat reported that no ref on origin held the work and offered a fresh run.
2. livespec-dev-tooling-ie7fas, run 01M74TQRCC64. Same comment. refs/heads/needs-human/2ad8033d8eb04b279c21de498e3b4c9b at 80d89606 held 2 files, +153/-12, including the hook-refused staged remainder. It was reported to the coordinator as a work-loss instance.
3. overseer-fbt5hu, run 01M74R70MKGG. Same comment. refs/heads/needs-human/7a55832bc9504ad186f093025eac443c at f583be9d held 3 files, +360. The item was regroomed into two new children on the reading that its staged implement was lost, which re-spends the work the ref already holds.

Instances 2 and 3 were raised by legacy-coordinator-agent as a P1 work-loss class, which it withdrew after the plan seat measured each ref with git ls-remote and a merge-base diff. The comment is literally correct: today's clause asks only for work-in-progress refs, and those ship with bd-ib-ofvsr3. The ref that does hold the work is named only in a different comment (the preservation line of livespec-needs-human-cause), so a reader of the preserved-tree comment alone concludes nothing was kept. Naming the size of the merge-base diff also gives the reader the empty-diff check directly. A preserved ref whose diff is empty preserves nothing, and the comment then says so in figures rather than by omission. Filed under plan factory-run-work-preservation (epic bd-ib-nckst7), with no objection from legacy-coordinator-agent (2026-11-11).

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance" → "A run's ending names its latest preserved capture on the item".**

Replace the sentence

> When the Dispatcher records a run's ending that is not a merge, or releases an item whose run is absent from its factory, it MUST list the run's work-in-progress refs on the forge and add one `livespec-preserved-tree` ledger comment to the item naming the run id, the factory name, the run's latest preserved capture and its commit id, or stating that the run has no work-in-progress ref.

with

> When the Dispatcher records a run's ending that is not a merge, or releases an item whose run is absent from its factory, it MUST list the run's work-in-progress refs on the forge and add one `livespec-preserved-tree` ledger comment to the item naming the run id, the factory name, the run's latest preserved capture and its commit id, or stating that the run has no work-in-progress ref. The comment MUST also name every needs-human ref and every failed-checkpoint preservation ref, as §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" defines them, that was published at the same run's ending, each with its tip commit id and the size of the diff between that tip and its merge-base with the default branch, stated as files changed, insertions and deletions and measured with the top-level `.fabro` directory excluded. When the run has no work-in-progress ref but such a ref exists, the comment MUST name that ref as the run's preserved work and MUST NOT consist only of the statement that the run has no work-in-progress ref. A preserved ref whose measured diff is empty MUST be named with that empty diff, so the comment states in figures that it preserves no change. When a ref's diff cannot be measured, the comment MUST name the ref and say that its diff could not be determined, which is distinct from an empty diff. When the run has neither a work-in-progress ref nor such a ref, the comment MUST say that the run preserved no tree.

Every other sentence of the paragraph is unchanged, including the could-not-be-determined case for an unreadable forge, the no-duplicate rule, and the template-opener and failure rules. The release rule of "Recovery from the failed run's preserved work" that reads this comment keys on a work-in-progress ref or an undetermined preservation, and it is unchanged.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 318 — A run's ending names its latest preserved capture on the item`.**

Append three scenarios to the Gherkin block, before the closing fence:

```gherkin
  Scenario: a needs-human ending with no capture names its needs-human ref and its diff
    Given a run of work item W that ended at needs_human with no work-in-progress ref
    And the ending published refs/heads/needs-human/<run-id> at commit N whose diff against its merge-base with the default branch, excluding .fabro, is 2 files with 153 insertions and 12 deletions
    When the Dispatcher records the run's ending
    Then W's livespec-preserved-tree ledger comment names refs/heads/needs-human/<run-id>, commit N, and 2 files, 153 insertions and 12 deletions
    And the comment does not consist only of the statement that the run has no work-in-progress ref

  Scenario: a needs-human ref with an empty diff is named with that empty diff
    Given a run of work item W that ended at needs_human with no work-in-progress ref
    And the ending published a needs-human ref whose diff against its merge-base, excluding .fabro, is empty
    When the Dispatcher records the run's ending
    Then W's livespec-preserved-tree ledger comment names that ref with 0 files changed

  Scenario: an unmeasurable needs-human diff is not reported as empty
    Given a run of work item W whose ending published a needs-human ref
    And the merge-base diff of that ref cannot be measured
    When the Dispatcher records the run's ending
    Then W's livespec-preserved-tree ledger comment names that ref and says its diff could not be determined
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
