---
topic: reconcile-merged-changes-that-added
author: claude-opus-5-5
created_at: 2026-11-12T17:55:00Z
---

## Proposal: A first drift run starts from a named baseline merge, and every filed drift finding ends in one of three recorded resolutions

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The drift run processes "every default-branch merge after the recorded frontier", but a repository whose detection-coverage anchor holds no completed drift record has no frontier. Nothing then says where its first run starts. The run also files a proposal per finding, but nothing says how a filed finding ENDS. This proposal makes a run with no prior frontier start only from a baseline merge the operator names, and refuse without one rather than scan the whole history. It also names three resolutions for a filed drift finding: a ratified clause, a merged removal, or an anchor comment recording accepted implementation detail beside a rejected proposal.

### Motivation

Work item bd-ib-76ztny (plan bd-ib-ax3rds): reconcile the merges since 2026-10-04 that added unspecified behaviour, and record the baseline frontier. It is held at spec-change tier for this linked stem: chore, verdict partial, spec 360, generalization target `## The skill surface`. The topic is the item's linked stem, so the hold links without a relink. Its dispatch stays gated on bd-ib-kojs3t (the cached prefix, #5054) by the coordinator ruling of 2026-11-01 on livespec-dev-tooling-dfixhe.

The tier record names three unstated parts. Two are general rules, stated below. The third, a reconciliation comment recording BCP14 clause and word counts before and after, is a report about this one plan's outcome, not a behaviour of the drift job. It belongs to the plan's own Proof of Done, so this proposal does not state it. Once this ratifies, the item's Definition of Done should move that bullet to the plan level; the coordinator rules on that.

Design choices, stated for the grade:
- **Refuse without a baseline.** Silently scanning every historical merge on a first run would file the whole history's drift in one pull request, which the queue cap exists to prevent. A named baseline is cheap to supply and is recorded.
- **The baseline is recorded once.** It is written in the run's attempt record, and the completed record that follows becomes the frontier exactly as today. No second mechanism moves the frontier.
- **Accepted detail needs a rejection too.** A comment alone would leave the proposal pending forever, so the third resolution pairs a revise rejection of the drift proposal with the anchor comment naming the finding identity.

In-flight alignment, all `align`: #5054 changes how the drift judge receives its spec prefix, not the run's scope or findings. Fleet scope: the drift job is the orchestrator Dispatcher's, so every tenant that enables a drift schedule inherits it.

### Proposed Changes

**1. Baseline and resolutions (`contracts.md` §"The skill surface", the "The drift run." bullet).** After the sentence ending "a later merge's success MUST NOT advance past it.", add:

> When the repository's detection-coverage anchor carries no completed drift record, a drift-job run MUST take its declared scope from a BASELINE merge the operator names on that run, and process every default-branch merge after it exactly as this bullet states. The run MUST record the baseline merge SHA and the operator in its attempt record. Without a named baseline, such a run MUST refuse, writing only an attempt record that names the missing baseline, and MUST NOT scan the default branch's whole history. Once a completed record exists, its frontier governs, and a named baseline MUST be refused. A filed drift finding is RESOLVED by exactly one of three outcomes. The first is a revise that accepts or modifies its proposal, amending the clause its generalization target names when that clause exists. The second is a merged pull request that removes the behaviour from the default branch. The third is a revise that rejects its proposal together with a ledger comment on the detection-coverage anchor that names the finding identity and records the behaviour as accepted implementation detail. A finding with none of these outcomes stays unresolved.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A first drift run starts from a named baseline merge, and a filed drift finding ends in one of three resolutions

```gherkin
Feature: a drift backfill has a stated start and every finding a stated end
  Scenario: a first run with a named baseline processes the merges after it
    Given a repository whose detection-coverage anchor holds no completed drift record
    When a drift-job run is invoked naming baseline merge B
    Then the run processes every default-branch merge after B in merge order
    And its attempt record names B and the operator

  Scenario: a first run without a baseline refuses
    Given a repository whose detection-coverage anchor holds no completed drift record
    When a drift-job run is invoked naming no baseline
    Then the run refuses, writing only an attempt record naming the missing baseline
    And no merge is judged

  Scenario: a named baseline is refused once a frontier exists
    Given a repository whose detection-coverage anchor holds a completed drift record
    When a drift-job run is invoked naming a baseline merge
    Then the run refuses the baseline and the recorded frontier is unchanged

  Scenario: a finding resolved as accepted implementation detail
    Given a filed drift finding whose proposal a revise rejected
    When the detection-coverage anchor gains a comment naming the finding identity and recording the behaviour as accepted implementation detail
    Then the finding reads resolved
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-76ztny"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. The row and entry MUST carry the heading as numbered at revise.
