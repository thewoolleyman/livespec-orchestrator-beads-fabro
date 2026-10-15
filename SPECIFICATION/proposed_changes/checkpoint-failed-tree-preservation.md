---
topic: checkpoint-failed-tree-preservation
author: claude-opus-5-5-plan-checkpoint-commit-hook-failures
created_at: 2026-10-15T12:57:51Z
---

## Proposal: A checkpoint-failed run's tree is published to a preservation ref when nothing else carries it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add one paragraph to contracts.md §"Failed engine checkpoint commit attribution", directly after the preserve-by-reference paragraph. When a run ends on a failed engine checkpoint and no observed terminal patch carries the failed node's work, the Dispatcher reads the run's changed files from the resolved factory and publishes them through the forge Git Data API (no push, no hooks) as one commit on refs/livespec/preserved-publish/<work-item-id>/<commit-sha>, parented on the run's base commit. A livespec-preserved-tree comment names the ref. A failure names the failed step and still rests the item at needs-human, and an observed terminal patch suppresses the ref. Add Scenario 183 exercising it, and a heading-coverage entry and debt row owned by work-item bd-ib-na2xvm.

### Motivation

Factory run 01M4ZSQWRT760E1C55C8ZCVZM1 (bd-ib-na2xvm, hp, 2026-10-15) ended at dod_gate with six coherence findings: the item's References line (Scenario 170) resolves but does not govern its preservation and recovery assertions, and the gate found no ratified heading that does. Scenario 170 and its clause govern ATTRIBUTION of a failed checkpoint and record the terminal patch's size and digest, but say nothing about recovering the tree when no terminal patch carries it (a stage diff artifact never does, because it holds only earlier checkpointed work). That is the case of run 01M4YJGC55V86C9V1X07QG3Y2H (bd-ib-54q7fn), whose roughly 47 minutes of implement work existed only in the stopped container and was rescued by hand through the same Git Data API route this paragraph now requires. The freeze driver (session gitops-fleet-capacity-monitoring) routed the gap spec-first under the maintainer's delegation recorded on livespec-dev-tooling-dfixhe.

### Proposed Changes

1. In SPECIFICATION/contracts.md, §"Failed engine checkpoint commit attribution", directly after the paragraph that begins "The run's work is preserved by reference through the existing preserve-by-reference pointer." (and before the next heading), insert this paragraph:

**A tree that nothing else carries is published to a preservation ref.** A failed checkpoint leaves the failed node's uncommitted work outside every stage diff artifact, so only the run's terminal patch can carry it. When a run ends on a failed engine checkpoint and the Dispatcher has not observed a terminal patch on the run's terminal `run.failed` event, the Dispatcher MUST read the run's changed files, with their contents, from the dispatch's resolved factory target, and MUST publish them as one commit at the ref `refs/livespec/preserved-publish/<work-item-id>/<commit-sha>` on the item's repository, where `<commit-sha>` is the published commit's own id. The commit's parent MUST be the run's base commit, which is the commit the dispatch's sandbox checked out as the dispatch record names it, and its tree MUST reflect every change the run made relative to that commit, removals included. The publication MUST create the blobs, the tree, the commit and the ref through the forge's Git Data API, and MUST NOT run `git push` or any repository hook. The published commit is a recovery artifact, not a commit to land: a seed taken from it under §"Recovery from the failed run's preserved work" MUST take its tree onto the base commit as uncommitted work, and MUST NOT carry the hookless commit itself. When the publication succeeds, the Dispatcher MUST add one ledger comment to the item, before the item's blocked transition, that opens with the marker line `livespec-preserved-tree` and names the run id, the factory name, the preservation ref and its commit id. When the changed files cannot be read, or any step of the publication fails, the Dispatcher MUST add a ledger comment with the same marker line stating that the tree was not preserved and naming the step that failed (the files read, a blob, the tree, the commit, or the ref), and the item MUST still rest `blocked` with `blocked_reason: needs-human`; a failed preservation MUST NOT change the dispatch outcome or its exit code. Either comment MUST carry names and figures only, MUST pass the shared template-opener detector before it is written, and, when it fails the detector or cannot be written, MUST be journaled with its reason and MUST NOT prevent the blocked transition. When the Dispatcher has observed a terminal patch on the run's terminal event, it MUST NOT create a preservation ref for that run, and the existing preserve-by-reference pointer with the patch's size and digest stands alone. A terminal patch the Dispatcher could not observe because the run's events cannot be read does not count as observed, so the publication above MUST be attempted: a duplicate preservation is recoverable, while a missed one is not. Scenario 183 in `scenarios.md` exercises this paragraph.

2. In SPECIFICATION/scenarios.md, after Scenario 181, append:

## Scenario 183 — A checkpoint-failed run whose tree nothing else carries is published to a preservation ref

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution".

```gherkin
Feature: The work of a run that ended on a failed engine checkpoint survives the run
  As the maintainer of a repository dispatched through the factory
  I want the changed files of a checkpoint-failed run published to a ref when no terminal patch carries them
  So that finished work is recoverable after the run's sandbox is gone

  Scenario: the changed files are published as one commit on a preservation ref
    Given a dispatched run that ended on a failed engine checkpoint commit of node implement
    And an earlier node of the run left a stage diff artifact
    And its terminal run.failed event carries no terminal patch
    When the Dispatcher reports the dispatch result
    Then it reads the run's changed files from the dispatch's resolved factory target
    And the forge carries a ref refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose commit's parent is the run's base commit and whose tree reflects every change the run made, removals included
    And no git push and no repository hook ran for that publication
    And a livespec-preserved-tree ledger comment names the run id, the factory, the preservation ref and its commit id
    And the item rests blocked with blocked_reason needs-human
    And the dispatch reports exit code 4

  Scenario: a failed preservation is reported and the item still rests at needs-human
    Given a dispatched run that ended on a failed engine checkpoint commit and whose terminal event carries no terminal patch
    And the factory refuses the read of the run's changed files
    When the Dispatcher reports the dispatch result
    Then no preservation ref is created
    And a livespec-preserved-tree ledger comment states that the tree was not preserved and names the files read as the step that failed
    And the item rests blocked with blocked_reason needs-human
    And the dispatch reports exit code 4

  Scenario: a run whose events cannot be read is still published
    Given a dispatched run that ended on a failed engine checkpoint commit
    And the run's events cannot be read from the dispatch's resolved factory target
    When the Dispatcher reports the dispatch result
    Then it attempts the publication of the run's changed files to a ref under refs/livespec/preserved-publish/<work-item-id>/
    And the item rests blocked with blocked_reason needs-human

  Scenario: a run whose terminal patch carries its work gets no preservation ref
    Given a dispatched run that ended on a failed engine checkpoint commit
    And its terminal run.failed event carries a terminal patch
    When the Dispatcher reports the dispatch result
    Then no ref under refs/livespec/preserved-publish/<work-item-id>/ is created for that run
    And the existing preserve-by-reference pointer and the terminal patch's size and digest are recorded as before
```

3. In tests/heading-coverage.json, append an entry for the new heading "## Scenario 183 — A checkpoint-failed run whose tree nothing else carries is published to a preservation ref" with spec_root "SPECIFICATION", spec_file "scenarios.md", test "TODO", work_item "bd-ib-na2xvm", and reason: "Ratified by the revision accepting proposal checkpoint-failed-tree-preservation (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq). The Dispatcher-side preservation is not implemented yet; an integration-tier test is owed for the four sub-scenarios, and work-item bd-ib-na2xvm implements them and owns that binding."

4. In tests/heading-coverage-debt.json, append a register row for the same heading with spec_root "SPECIFICATION", spec_file "scenarios.md", work_item "bd-ib-na2xvm" and first_seen set to the revision date, as the v142 revision did for Scenario 180.

Numbering: Scenario 182 is reserved by the pending proposal factory-addresses-from-a-gitops-registry, so this proposal takes 183. If the revise pass finds 183 taken, it takes the next free number and updates the contracts.md cross-reference, the heading-coverage entry and the heading-coverage-debt register row to match.

