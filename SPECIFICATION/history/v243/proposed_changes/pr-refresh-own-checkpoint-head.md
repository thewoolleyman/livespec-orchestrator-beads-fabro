---
topic: pr-refresh-own-checkpoint-head
author: claude-opus-5-5
created_at: 2026-10-27T03:05:16Z
---

## Proposal: pr_refresh treats origin's publish head as its own when it adds only this run's empty engine checkpoint commits

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under 'Scripted publication and proof-head integrity', a publish head on origin that descends from the run's previously published head, and adds only engine checkpoint commits of this run that change no tree, is neither foreign nor unexpectedly changed. pr_refresh takes that observed head as the recorded remote head for its lease, and treats the added commits as the run's own empty commits under the existing unchanged-head rule (Scenario 226), which drops them and carries the proof forward. Any other addition, or a head that does not descend from the published head, still fails closed as foreign.

### Motivation

Spec-first for work-item bd-ib-qxq4jb (P1, held for dispatch; coordinator gitops-fleet-capacity-monitoring ruling R93; requested by petri-factory-on-gmktec). On the Petri engine the run branch tracks the publish branch, so node checkpoint commits are pushed onto it. Measured 2026-10-27 on bd-ib-qksrl6, run 01M5XFBSKGY0JXA30MQNWER2V9: pr_refresh@1 republished at 7e89feeb and routed back with reproof_required. The engine then pushed 454c6d82 'fabro(<run>): pr_refresh (success)' and f301f206 'fabro(<run>): pr_refresh_head (failure)' onto origin feat/bd-ib-qksrl6. Both commits are empty: zero files, and the same tree 5e8a3f4b as 7e89feeb, read from the forge's compare and commit endpoints. After the proof loop passed, pr_refresh@2 failed with LIVESPEC_PR_REFRESH_FOREIGN_HEAD on its own head, and the run ended at needs_human. The ratified text requires a 'foreign or unexpectedly changed publish head' to fail closed but does not say that the run's own empty checkpoint commits are neither. Prior art: bd-ib-reapbq (strip empty commits on the unchanged path), bd-ib-myvlbl (closed; drop empty checkpoints by rebasing) and bd-ib-m6sdjh (a checkpoint masks a node's failure). The clause is restricted to EMPTY checkpoint commits, so a tree change the proof never saw can never be adopted as the run's own.

### Proposed Changes

Two coordinated edits; both MUST land together in a single revision. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", the paragraph **Scripted publication and proof-head integrity.**** Immediately after its last sentence

```
recognized idempotently from durable run provenance and matching remote state.
```

insert

```
A publish head on origin that differs from the run's previously published head
is neither foreign nor unexpectedly changed when it descends from that head and
every commit it adds is an engine checkpoint commit of this run that changes no
tree, its message naming this run's id. `pr_refresh` MUST then take that
observed head as the recorded remote head of the run's publish branch for every
lease this section requires, and MUST treat the added commits as the run's own
empty commits under the unchanged-head rule below. A head that adds any other
commit, or that does not descend from the run's previously published head,
remains foreign. Measured 2026-10-27 on run 01M5XFBSKGY0 (bd-ib-qksrl6): after
`pr_refresh` republished at 7e89feeb and routed back for reproof, the engine
pushed two empty checkpoint commits of the same run onto origin's publish
branch, and the next `pr_refresh` failed closed on that head as foreign.
Scenario 226 in `scenarios.md` exercises this sentence.
```

**2. `SPECIFICATION/scenarios.md` §"Scenario 226 — An unchanged refresh strips the run's empty commits and carries the proof forward".** Inside the gherkin block, after the scenario "A head with no empty commits is left alone", append

```gherkin
  Scenario: The run's own empty checkpoint commits on origin are not a foreign head
    Given pr_refresh republished the run's head and the run routed back for reproof
    And origin's publish branch now descends from that published head, adding only empty engine checkpoint commits of this run
    When pr_refresh runs again after the proof loop passes
    Then it does not fail closed on a foreign publish head
    And it republishes the head without those commits under an explicit lease naming the observed origin head

  Scenario: Any other addition to origin's publish branch is still foreign
    Given origin's publish branch adds to the run's published head a commit that is not an empty engine checkpoint commit of this run, or does not descend from that head
    When pr_refresh runs
    Then it fails closed on a foreign publish head
```

