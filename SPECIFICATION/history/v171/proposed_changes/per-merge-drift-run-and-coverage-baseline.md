---
topic: per-merge-drift-run-and-coverage-baseline
author: claude-fable-5-1:spec-implementation-lockstep
created_at: 2026-10-20T01:08:21Z
---

## Proposal: The drift binding becomes a per-merge run behind a contiguous coverage frontier, with filing unattended and acceptance human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The merge-count drift binding stops being a reminder and becomes a run. Each reconcile pass enumerates the default-branch merges after a recorded, contiguous coverage frontier, runs the drift pass over each merge's diff through the shared spec-stated judgement, files one proposed change per partial or unstated behaviour naming the generalization target, holds findings beyond a configurable open-proposal cap on the detection-coverage anchor, and advances the frontier only past merges whose every finding is filed or held. The post-merge janitor is one caller of the same primitive. Filing is the machine path livespec core already permits; acceptance of a drift-origin proposal stays human at revise. The ledger-intent scan of capture-spec-drift uses the same judgement. The agent-written sentence that forbade every unattended detector run is replaced by the ratified boundary.

### Motivation

Plan spec-implementation-lockstep (epic bd-ib-ax3rds), Definition of Done assertions 4 and 9, from the maintainer's 2026-10-19 ruling that implementation and specification are kept in sync in a virtuous feedback loop. Measured 2026-10-19 in this repository: the detection-coverage anchor bd-ib-j5fzyo carries zero capture-spec-drift records, dispatcher.drift_capture_merge_threshold is 1, and no drift pass has ever completed, so the binding the maintainer ruled on 2026-08-25 (drift capture bound to a merge count, default 1) never turned the loop. The sentence 'nothing in this section runs a detector headlessly, and no policy setting MAY do so' was written by an agent in v078 and ratified under delegated authority; no maintainer ruling against unattended detection exists, while livespec core's spec.md states 'Orchestrators MAY file drift (the machine path); an orchestrator executor MUST NOT accept it' and this repository's spec.md states the Dispatcher MAY file impl→spec drift. The independent review of the plan's scoping (research note 004) required a contiguous frontier so a later successful pass cannot skip a failed merge, an enumerator that covers merges no dispatch janitor sees, and a bounded proposal queue because every proposal costs an independent review.

### Proposed Changes

In SPECIFICATION/contracts.md, section "The skill surface" → "Heavyweight authored skills" → "capture-spec-drift", first paragraph, replace "Detect impl → spec drift heuristically (LLM-driven)." with "Detect impl → spec drift through the spec-stated judgement of the `livespec_runtime.spec_stated` module (the one judgement every orchestrator shares, which answers whether a behaviour is stated by the ratified specification and names the heading whose generalization would state it)." In the paragraph beginning "`capture-spec-drift` MUST detect drift from two sources", after "NOT reflected in the current spec." insert: "Whether intent is reflected MUST be decided by the same spec-stated judgement, over every live work-item and every work-item captured on or after the latest version's cut, reading the four fields named above; an item's type is never a detection exclusion."

In SPECIFICATION/contracts.md, section "The skill surface" → "Heavyweight authored skills" → "Detection coverage records and staleness facts":

1. In the "**Records.**" bullet, replace "or the default-branch merge SHA the drift pass ran through" with "or, for the drift pass, the FRONTIER: the newest default-branch merge SHA such that it and every earlier merge after the previous frontier has been processed with every finding filed or held".

2. Replace the "**Drift staleness.**" bullet with: "**The drift run.** Each reconcile pass of the Dispatcher MUST enumerate every default-branch merge after the recorded frontier, in merge order, and MUST run the drift pass over each merge's diff through the spec-stated judgement; the post-merge janitor MAY call the same primitive after its own merge, and a merge no janitor saw — a hand merge, a spec pull request, an externally merged pull request — is processed by the next reconcile pass. For each `partial` or `unstated` behaviour a merge adds, the pass MUST file one proposed change carrying a drift origin and naming the generalization target, through the cross-boundary propose-change handoff, with a finding identity derived from the merge and the behaviour so that a retried pass files no duplicate. The frontier MUST advance to a merge only when every finding of that merge and of every earlier merge is filed or held; a merge whose pass fails stops the frontier until it succeeds, and a later merge's success MUST NOT advance past it. The pass MUST NOT accept, modify or reject any proposal. When the count of default-branch merges after the frontier is at or past the effective `dispatcher.drift_capture_merge_threshold`, the needs-attention snapshot MUST still carry a drift-staleness fact naming the merges after the frontier, so an unrun or failing pass is visible; merge counting excludes nothing silently."

3. Add after it: "**`dispatcher.drift_proposal_queue_cap`** (sourced from this repo's `.livespec.jsonc`, positive integer, default **5**) — the number of drift-origin proposed changes that MAY be open at once. When the cap is reached, further findings MUST be HELD on the detection-coverage anchor with their identities rather than filed, the frontier MUST NOT advance past a merge with a held finding, and `needs-attention` MUST list the held findings with a handoff naming `revise`. Declared **API-configurable** like the threshold above; no per-item override."

4. Replace the "**Consent is untouched.**" bullet with: "**Filing is the machine path; acceptance is human.** `capture-impl-gaps` remains a consent-gated attended dialogue, and a gap-capture staleness fact is a surfaced, owned TRIGGER that runs nothing. The drift run above files unattended, which livespec core's `spec.md` permits (\"Orchestrators MAY file drift (the machine path)\"); what it MUST NEVER do is accept a proposal: acceptance of a drift-origin proposal rests at `revise` with its human gate, and no `revise_decision_mode` value accepts a drift-origin proposal."

In SPECIFICATION/scenarios.md, under "## Scenario 82 — Staleness facts surface owned triggers, never headless runs" (the heading is unchanged; the entry in tests/heading-coverage.json MUST be re-bound in the same revise to the test that exercises the amended drift case), replace the sub-scenario "Merges past the threshold surface the drift fact" with:

```gherkin
Scenario: Merges past the threshold surface the drift fact while the run has not caught up
  Given default-branch merges after the recorded drift frontier at or past the effective threshold
  When needs-attention composes the snapshot
  Then a drift-staleness fact appears naming the merges after the frontier
  And the fact invokes no detector; the reconcile pass is what runs the drift pass
```

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts

```gherkin
Feature: Implementation that outruns the specification is caught at every merge
  As the maintainer keeping the specification honest against the implementation
  I want every default-branch merge judged against the ratified spec and its unstated behaviour proposed
  So that the feedback loop turns without a session and without a human accepting anything by machine

  Scenario: A merge adding unstated behaviour files one proposal and advances the frontier
    Given a recorded drift frontier and one later default-branch merge whose diff adds a behaviour the spec-stated judgement reports unstated
    When the reconcile pass runs
    Then one proposed change with a drift origin is filed naming the generalization target
    And a completed drift coverage record names that merge as the frontier

  Scenario: A failed merge stops the frontier under a later success
    Given two merges after the frontier where the pass over the first fails and the pass over the second succeeds
    When the reconcile pass runs
    Then the frontier does not advance past the first merge
    And an attempt record names the failed merge
    And the drift-staleness fact still names both merges

  Scenario: A retried pass files no duplicate
    Given a merge whose finding was already filed under its finding identity
    When the reconcile pass processes the merge again
    Then no second proposed change is filed for that finding

  Scenario: Findings beyond the queue cap are held, not filed
    Given dispatcher.drift_proposal_queue_cap open drift-origin proposals
    When a merge adds another unstated behaviour
    Then the finding is held on the detection-coverage anchor with its identity
    And the frontier does not advance past that merge
    And needs-attention lists the held finding with a handoff naming revise

  Scenario: A merge no janitor saw is processed
    Given a spec pull request merged by hand after the frontier
    When the next reconcile pass runs
    Then that merge is processed exactly as a dispatched merge

  Scenario: The pass never accepts a proposal
    Given a drift-origin proposed change filed by the pass
    When the pass completes
    Then the proposal rests under proposed_changes for revise and its decision is taken by no machine
```
