---
topic: the-engine-s-per-stage
author: claude-opus-5-5
created_at: 2026-11-12T11:46:11Z
---

## Proposal: An engine checkpoint never moves a run branch under an open merge or rebase

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The engine's per-stage checkpoint MUST NOT write to the run branch while a merge or rebase is in progress in the run's working tree. It defers the checkpoint, records a checkpoint-deferred event naming the node and the operation, and writes the deferred checkpoint at the first later checkpoint point with no operation in progress. A deferral is not a checkpoint failure.

### Motivation

No ratified clause states when the engine may checkpoint (the filing-stage spec-change-tier record on bd-ib-rhv4lo). All 5 instances in bd-ib-ebwpxw's 72 h census of commit settle nodes whose git rebase --continue did not complete share one sequence: a rebase of the run branch open at turn end, then 2-3 new engine checkpoint commits on that branch, then a failed continue. Two of the five carry git's own update_ref error. bd-ib-ebwpxw (proposal a-commit-settle-node-whose, #5035) makes the settle node fail closed on that symptom. bd-ib-mx2h62 (#5045) removes the agent's interactive rebases, which covers 2 of the 5. This clause prevents the cause in all 5. Satisfying it requires a Fabro fork change, so per legacy-coordinator-agent (session 245a3c34, about 11:50Z 2026-11-12) this proposal takes NO revise slot until the maintainer approves starting that build. It is filed now as a draft for grading only. Work item bd-ib-rhv4lo.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`, §"Failed engine checkpoint commit attribution".** Insert this paragraph immediately AFTER that subsection's first paragraph, the one that begins "A Fabro run ENDS ON A FAILED ENGINE CHECKPOINT", and BEFORE the paragraph that begins "The Dispatcher MUST recognize such a run from the run's event stream":

> **An engine checkpoint never moves a run branch under an open merge or rebase.** The engine checkpoint this subsection defines MUST NOT write a commit to the run branch while the run's working tree has a merge or rebase in progress, that is, while `rebase-merge` or `rebase-apply` exists under its git directory or `MERGE_HEAD` exists. In that state the engine MUST defer the node's checkpoint and leave the run branch ref unchanged. It MUST record a checkpoint-deferred event in the run's event stream naming the node and the in-progress operation, and MUST write the deferred checkpoint at the first later checkpoint point at which no merge or rebase is in progress. A deferred checkpoint is not a failed checkpoint: it MUST NOT produce a `checkpoint.failed` event and MUST NOT end the run. The rule holds on every Fabro instance the fleet runs. Measured 2026-11-12 over five runs in which a commit settle node's `git rebase --continue` did not complete (bd-ib-reuccp, livespec-dev-tooling-h2i4u2, livespec-dev-tooling-xtofr3, bd-ib-rzkhqv, livespec-dev-tooling-5lhafp): in each, the agent turn ended with a rebase of the run branch open, and the engine then wrote two or three new checkpoint commits to that branch. On rzkhqv and 5lhafp, git's own error records the cause, `update_ref failed ... is at <checkpoint> but expected <pre-rebase head>`. Scenario 170 in `scenarios.md` exercises this paragraph.

**Edit 2 — `SPECIFICATION/scenarios.md`, §"Scenario 170 — A failed engine checkpoint commit names its node and cause and rests the item at needs-human".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "an earlier classification keeps its route". The scenario's heading is unchanged.

```gherkin
  Scenario: A checkpoint is deferred while a rebase is in progress
    Given a run whose agent stage ends while a rebase of the run branch it started is still in progress
    When the engine reaches that node's checkpoint
    Then the run branch ref is unchanged
    And the run's event stream records a checkpoint-deferred event naming the node and the in-progress rebase
    And no checkpoint.failed event is recorded

  Scenario: A deferred checkpoint is written once no operation is in progress
    Given a run whose checkpoint was deferred while a rebase was in progress
    And the commit settle node's git rebase --continue completed with no update_ref failure
    When the engine reaches its next checkpoint point
    Then the engine writes the deferred checkpoint to the run branch
```

After ratification, bd-ib-rhv4lo's `References:` line is repointed from Scenario 179 to Scenario 170.
