---
topic: factory-run-recovery-release-on-any-unmerged-ending
author: claude-opus-5-5
created_at: 2026-11-05T20:40:45Z
---

## Proposal: Release for recovery any unmerged ending whose run holds a preserved capture

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen the recovery-release condition of "Recovery from the failed run's preserved work" so that an item whose latest dispatch ended without merging, and whose ledger carries a livespec-preserved-tree receipt naming that run's work-in-progress ref (or stating its preservation could not be determined), is released for recovery once it is at ready. A factory restart cancel, a cancel made outside the Dispatcher, and a returned wall-budget cancel are then routed by recovery routing, seeded from the run's latest preserved capture, instead of fresh. A Scenario 319 case is added for the restart cancel and the wall-budget return.

### Motivation

Maintainer ruling, 2026-11-05, plan factory-run-work-preservation (epic bd-ib-nckst7, scope event frwp-ruling-recovery-release-2026-11-05): the maintainer chose "Any unmerged ending (Recommended)" from the options in plan/factory-run-work-preservation/research/006-recovery-release-scope-gap-2026-11-05.md. The chosen option reads: "Any ending that didn't merge, where the run has saved work, counts as released for recovery. Existing safety checks still choose resume, seed, fresh or hold. One spec clause, one Scenario 319 case, one assertion on bd-ib-v6br5b. Makes plan assertion 2 true as written."

Measured gap (legacy-coordinator-agent, 2026-11-05): after the 16:14Z restart of the petri server (:32276), the runs it cancelled relaunched fresh. The release list in this clause names only a first-stall release, provider-limit and adapter-launch releases, stale-assignee clearance, and the needs_human and non_converged terminals. The Dispatcher's released_for_recovery (.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_recovery_release.py) matches that list. A restart cancel of a run that was not janitor-green, a cancel made outside the Dispatcher, and a wall-budget cancel are not in it, so "An item not released for recovery is routed fresh" applies. Once v306's work-in-progress refs (Scenario 317) ship, those runs' settled work would sit on origin and no re-dispatch would use it. That contradicts plan assertion 2: "A re-dispatch of an item whose earlier run ended without merging starts from that run's preserved tree". The release is keyed off the Scenario 318 receipt, which the Dispatcher already writes at every non-merge ending, so a future ending needs no new list entry and the release decision stays a ledger read.

### Proposed Changes

Two edits. Every other sentence of the edited paragraphs is unchanged.

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".**

Immediately after the sentence that releases an item whose latest journaled dispatch ended at the workflow's `needs_human` terminal or at a `non_converged` terminal (the sentence ending "... and no newer dispatch has been submitted for it."), insert:

> An item is also released for recovery when its latest journaled dispatch ended by any route other than a merge of its pull request, the item carries a `livespec-preserved-tree` ledger comment under §"Dispatcher admission, WIP cap, and post-merge acceptance" → "A run's ending names its latest preserved capture on the item" that names that dispatch's run and either names a work-in-progress ref of that run or states that the run's preservation could not be determined, the item is at `ready` by any path (the Dispatcher's own return after a cancel, a human valve, a groom, or a return from `backlog`), and no newer dispatch has been submitted for it. *Any route* includes a factory restart cancel of a run that was not janitor-green, a cancel made outside the Dispatcher, and a whole-run wall-budget cancel once a person has returned the item to `ready`. This sentence MUST NOT move an item out of `blocked`: an item that the wall budget rests for a person is released only after that person returns it to `ready`. The release MUST read the ledger comment only, so deciding it takes no remote measurement. Every sentence that follows, from "For such an item, the pre-claim refusal of §\"Across-dispatch required-result progress\" MUST be graded BEFORE recovery routing" through "... the needs-human or non-convergence cause recorded on the item.", MUST apply to an item this sentence releases exactly as it applies to an item the preceding sentence releases: the pre-claim refusal is graded first, the release consumes no budget of §"The three rework caps", routing measures the preserved work on origin before it seeds, a measurement that cannot be taken is the `held` outcome and never `fresh`, and a needs-human ref or preservation ref published at the same run's ending is preferred over the run's latest preserved capture. The goal brief of a `seeded` dispatch of such an item SHOULD name the ending it recovers from.

The routing outcomes (`resume`, `seeded`, `fresh`, `held`), the preserved-work preference order, and the sentence "An item not released for recovery is routed `fresh` without any remote measurement." are unchanged.

This sentence is independent of the pending proposal `a-plain-re-dispatch-of` (filed 2026-11-03), which widens the `needs_human` / `non_converged` sentence itself to any ending after the run published a head. The two releases MAY both hold for one item, and either one releases it. Whichever proposal is revised first, the other's text MUST still apply unchanged.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 319 — A re-dispatch starts from the latest run's latest preserved capture`.**

Append these two scenarios at the end of the existing gherkin fence. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: a run a factory restart cancelled before janitor succeeded is seeded from its latest capture
    Given work item W whose latest run R settled its implement commit, which origin holds at refs/livespec/wip/W/R/1
    And a factory restart cancelled R during its fix visit, before its janitor stage succeeded, so no preservation ref was published at R's ending
    And W carries a livespec-preserved-tree comment naming run R and refs/livespec/wip/W/R/1
    And W is at ready and no newer dispatch has been submitted for it
    When the Dispatcher next dispatches W
    Then W is graded by recovery routing before admission
    And it is routed seeded from refs/livespec/wip/W/R/1, not fresh

  Scenario: a wall-budget cancel stays blocked and is seeded only after a person returns it
    Given work item W whose latest run R was cancelled by the whole-run wall budget after its implement commit settled at refs/livespec/wip/W/R/1
    And W carries a livespec-preserved-tree comment naming run R and refs/livespec/wip/W/R/1
    When the Dispatcher's next pass runs while W rests blocked with blocked_reason needs-human
    Then W stays blocked and is not dispatched
    When a person returns W to ready and the Dispatcher next dispatches W
    Then it is routed seeded from refs/livespec/wip/W/R/1, not fresh
```

