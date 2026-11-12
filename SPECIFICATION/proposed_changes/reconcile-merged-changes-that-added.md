---
topic: reconcile-merged-changes-that-added
author: claude-opus-5-5
created_at: 2026-11-12T17:55:00Z
---

## Proposal: A first drift run starts from a named start merge, and every filed drift finding ends in one of three recorded resolutions

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The drift run processes "every default-branch merge after the recorded frontier", but a repository whose detection-coverage anchor holds no completed drift record has no frontier. Nothing then says where its first run starts. The run also files a proposal per finding, but nothing says how a filed finding ENDS. This proposal makes a run with no prior frontier start only from a start merge the operator names, and refuse without one rather than scan the whole history. It also names three resolutions for a filed drift finding: a ratified clause, a merged removal, or an anchor comment recording accepted implementation detail beside a rejected proposal.

### Motivation

Work item bd-ib-76ztny (plan bd-ib-ax3rds): reconcile the merges since 2026-10-04 that added unspecified behaviour, and record the baseline frontier. It is held at spec-change tier for this linked stem: chore, verdict partial, spec 360, generalization target `## The skill surface`. The topic is the item's linked stem, so the hold links without a relink. Its dispatch stays gated on bd-ib-kojs3t (the cached prefix, #5054) by the coordinator ruling of 2026-11-01 on livespec-dev-tooling-dfixhe.

The tier record names three unstated parts. Two are general rules, stated below. The third, a reconciliation comment recording BCP14 clause and word counts before and after, is a report about this one plan's outcome, not a behaviour of the drift job. It belongs to the plan's own Proof of Done, so this proposal does not state it. Once this ratifies, the item's Definition of Done should move that bullet to the plan level; the coordinator rules on that.

Design choices, stated for the grade:
- **Refuse without a start merge.** Silently scanning every historical merge on a first run would file the whole history's drift in one pull request, which the queue cap exists to prevent.
- **The start merge persists until a frontier exists** (grade fix 1). A long backfill against the queue cap holds findings, so it writes no completed record. Later runs therefore take the start merge from the newest attempt record that names one, rather than refusing.
- **One missing-start record** (grade fix 2), matching the code (`_dispatcher_reconcile_drift_lane.py:204-226`), which writes it once and reports it every tick.
- **"Start merge", not "baseline"** (grade fix 3). The item's "baseline merge" is the END frontier the backfill reaches; this clause names where it begins.
- **Accepted detail needs a rejection too.** A comment alone would leave the proposal pending forever, so the third resolution pairs a revise rejection of the drift proposal with the anchor comment naming the finding identity.

In-flight alignment, all `align`: #5054 changes how the drift judge receives its spec prefix, not the run's scope or findings. Fleet scope: the drift job is the orchestrator Dispatcher's, so every tenant that enables a drift schedule inherits it.

### Proposed Changes

**1. Start merge and resolutions (`contracts.md` §"The skill surface", the "The drift run." bullet).** After the sentence ending "a later merge's success MUST NOT advance past it.", add:

> When the repository's detection-coverage anchor carries no completed drift record, a drift-job run MUST take its declared scope from a START MERGE: the merge an operator names with `dispatcher.py drift-run --start <merge-sha>`, or else the start merge named by the newest attempt record on the anchor that carries one. It MUST process every default-branch merge after that start merge exactly as this bullet states. The attempt record of a run invoked with `--start` MUST record the start merge SHA and the run's `--invoker`. With no start merge from either source, the run MUST refuse and MUST NOT scan the default branch's whole history. As a stated exception to the attempt-record rule of the detection-coverage anchor, such refusals append at most one missing-start attempt record per anchor, and every refusal still reports the missing start merge in its outcome. Once a completed record exists, its frontier governs, and `--start` MUST be refused. A filed drift finding is RESOLVED by exactly one of three outcomes: a revise that accepts or modifies its proposal; a merged pull request that removes the behaviour from the default branch; or a revise that rejects its proposal together with a ledger comment on the detection-coverage anchor that names the finding identity and records the behaviour as accepted implementation detail.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A first drift run starts from a named start merge, and a filed drift finding ends in one of three resolutions

```gherkin
Feature: a drift backfill has a stated start and every finding a stated end
  Scenario: a first run with a named start merge processes the merges after it
    Given a repository whose detection-coverage anchor holds no completed drift record
    When drift-run is invoked with --start naming merge M
    Then the run processes every default-branch merge after M in merge order
    And its attempt record names M and the run's invoker

  Scenario: a later run before any completed record reuses the recorded start merge
    Given an anchor with no completed drift record whose newest start-carrying attempt record names merge M
    When drift-run is invoked with no --start
    Then the run takes M as its start merge

  Scenario: a run with no start merge refuses, recording it once
    Given an anchor with no completed drift record and no attempt record naming a start merge
    When drift-run is invoked twice with no --start
    Then each run refuses and reports the missing start merge, and no merge is judged
    And the anchor gains at most one missing-start attempt record

  Scenario: --start is refused once a frontier exists
    Given an anchor holding a completed drift record
    When drift-run is invoked with --start
    Then the run refuses the start merge and the recorded frontier is unchanged
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-76ztny"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. The row and entry MUST carry the heading as numbered at revise.
