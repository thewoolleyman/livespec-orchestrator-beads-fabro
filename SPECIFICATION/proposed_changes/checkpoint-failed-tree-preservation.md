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

Add one paragraph to contracts.md §"Failed engine checkpoint commit attribution", directly after the preserve-by-reference paragraph. It requires that when a run ends on a failed engine checkpoint and nothing else carries its work (no terminal patch, no stage diff artifact), the Dispatcher reads the run's changed files from the resolved factory and publishes them through the forge Git Data API as one commit on refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose parent is the run's base commit. A livespec-preserve-by-reference comment names the ref. A failure names the failed step and still rests the item at needs-human, and no second ref is created when another artifact carries the work. Add Scenario 183 exercising it, and a heading-coverage entry and debt row owned by work-item bd-ib-na2xvm.

### Motivation

Factory run 01M4ZSQWRT760E1C55C8ZCVZM1 (bd-ib-na2xvm, hp, 2026-10-15) ended at dod_gate with six coherence findings: the item's References line (Scenario 170) resolves but does not govern its preservation and recovery assertions, and the gate found no ratified heading that does. Scenario 170 and its clause govern ATTRIBUTION of a failed checkpoint and record the terminal patch's size and digest, but say nothing about recovering the tree when no patch and no stage diff exist. That is the case of run 01M4YJGC55V86C9V1X07QG3Y2H (bd-ib-54q7fn), whose roughly 47 minutes of implement work existed only in the stopped container and was rescued by hand through the same Git Data API route this paragraph now requires. The freeze driver (session gitops-fleet-capacity-monitoring) routed the gap spec-first under the maintainer's delegation recorded on livespec-dev-tooling-dfixhe.

### Proposed Changes

1. In SPECIFICATION/contracts.md, §"Failed engine checkpoint commit attribution", directly after the paragraph that begins "The run's work is preserved by reference through the existing preserve-by-reference pointer." (and before the next heading), insert this paragraph:

**A tree that nothing else carries is published to a preservation ref.** When a run ends on a failed engine checkpoint and the Dispatcher has observed that the run's terminal `run.failed` event carries no terminal patch and that the run left no stage diff artifact, the Dispatcher MUST read the run's changed files, with their contents, from the dispatch's resolved factory target, and MUST publish them as one commit, whose parent is the run's base commit, at the ref `refs/livespec/preserved-publish/<work-item-id>/<commit-sha>` on the item's repository, where `<commit-sha>` is the published commit's own id. The publication MUST create the blobs, the tree, the commit and the ref through the forge's Git Data API, and MUST NOT run `git push` or any repository hook. When the publication succeeds, the Dispatcher MUST add one ledger comment to the item, before the item's blocked transition, that opens with the marker line `livespec-preserve-by-reference` and names the run id, the factory name, the preservation ref and its commit id. When the changed files cannot be read, or any step of the publication fails, the Dispatcher MUST add a ledger comment stating that the tree was not preserved and naming the step that failed (the files read, a blob, the tree, the commit, or the ref), and the item MUST still rest `blocked` with `blocked_reason: needs-human`; a failed preservation MUST NOT change the dispatch outcome or its exit code. When the run's terminal event carries a terminal patch, or the run left a stage diff artifact, the Dispatcher MUST NOT create a preservation ref for that run, and the existing preserve-by-reference pointer stands alone. When the run's events cannot be read, the terminal patch is unobserved rather than absent, and the Dispatcher MUST attempt the publication as if it were absent. Scenario 183 in `scenarios.md` exercises this paragraph.

2. In SPECIFICATION/scenarios.md, after Scenario 181, append:

## Scenario 183 — A checkpoint-failed run whose tree nothing else carries is published to a preservation ref

```gherkin
Feature: The work of a run that ended on a failed engine checkpoint survives the run
  As the maintainer of a repository dispatched through the factory
  I want the changed files of a checkpoint-failed run published to a ref when nothing else carries them
  So that finished work is recoverable after the run's sandbox is gone

  Scenario: the changed files are published as one commit on a preservation ref
    Given a dispatched run that ended on a failed engine checkpoint commit of node implement
    And its terminal run.failed event carries no terminal patch
    And the run left no stage diff artifact
    When the Dispatcher reports the dispatch result
    Then it reads the run's changed files from the dispatch's resolved factory target
    And the forge carries a ref refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose commit's parent is the run's base commit and whose tree holds every changed file
    And no git push and no repository hook ran for that publication
    And a livespec-preserve-by-reference ledger comment names the run id, the factory, the preservation ref and its commit id
    And the item rests blocked with blocked_reason needs-human

  Scenario: a failed preservation is reported and the item still rests at needs-human
    Given a dispatched run that ended on a failed engine checkpoint commit and carries no terminal patch and no stage diff artifact
    And the factory refuses the read of the run's changed files
    When the Dispatcher reports the dispatch result
    Then no preservation ref is created
    And the item's ledger comment states that the tree was not preserved and names the files read as the step that failed
    And the item rests blocked with blocked_reason needs-human
    And the dispatch reports exit code 4

  Scenario: a run whose work another artifact carries gets no second ref
    Given a dispatched run that ended on a failed engine checkpoint commit
    And its terminal run.failed event carries a terminal patch
    When the Dispatcher reports the dispatch result
    Then no ref under refs/livespec/preserved-publish/<work-item-id>/ is created for that run
    And the existing preserve-by-reference pointer and the terminal patch's size and digest are recorded as before
```

3. In tests/heading-coverage.json, append an entry for the new heading "## Scenario 183 — A checkpoint-failed run whose tree nothing else carries is published to a preservation ref" with spec_root "SPECIFICATION", spec_file "scenarios.md", test "TODO", work_item "bd-ib-na2xvm", and reason: "Ratified by the revision accepting proposal checkpoint-failed-tree-preservation (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq). The Dispatcher-side preservation is not implemented yet; an integration-tier test is owed for the three sub-scenarios, and work-item bd-ib-na2xvm implements them and owns that binding."

4. In tests/heading-coverage-debt.json, append a register row for the same heading with spec_root "SPECIFICATION", spec_file "scenarios.md", work_item "bd-ib-na2xvm" and first_seen set to the revision date, as the v142 revision did for Scenario 180.

Numbering: Scenario 182 is reserved by two pending proposals (factory-addresses-from-a-gitops-registry and session-headroom-burn-projection-v2), so this proposal takes 183. If the revise pass finds 183 taken, it takes the next free number and updates the contracts.md cross-reference, the heading-coverage entry and the heading-coverage-debt register row to match.

