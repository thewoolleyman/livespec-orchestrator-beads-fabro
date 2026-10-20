---
topic: refresh-strips-run-empty-commits
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:42:51Z
---

## Proposal: An unchanged refresh strips the run's empty commits and republishes under lease

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Scripted publication and proof-head integrity" says "An unchanged head proceeds to `pr`". On the Petri-era engine, a run's published head can carry the engine's own EMPTY checkpoint commits even when the default branch did not advance, and those commits then reach the merged history. This proposal amends that sentence. When the default branch is already contained in the published head and that head carries any of the run's empty commits, `pr_refresh` republishes the head without them, under the explicit lease the paragraph already requires. Because the tree is identical to the proof-verified tree, the rewrite carries the verified proof forward instead of re-proving. A head with no empty commits still proceeds unchanged.

### Motivation

Work-item bd-ib-reapbq (plan fabro-currency, bd-ib-6tcjfx), released from pending-approval on 2026-10-16 under the maintainer's scope event recorded on livespec-dev-tooling-dfixhe. Its Definition of Done names this exact behaviour and cannot pass a dod_gate while the ratified sentence says an unchanged head proceeds untouched. Plan spec-implementation-lockstep R1 batch 6 routes it here as an amendment of that one sentence.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Definition-of-Done and Proof-of-Done stages", paragraph "**Scripted publication and proof-head integrity.**", replace the sentence "An unchanged head proceeds to `pr`." with:

> An unchanged head proceeds to `pr`, except that when the default branch is already contained in the published head and that head carries any of the run's own empty commits, `pr_refresh` MUST republish the head without them, under the explicit lease against the recorded remote head of the run's publish branch that this paragraph requires. A rewrite whose only change is dropping empty commits, over a tree identical to the proof-verified tree, MUST take the `carried_forward` decision of "Proof carry-forward across a refresh" and MUST NOT re-prove. A head carrying none of the run's empty commits MUST NOT be republished. Scenario 226 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 226 — An unchanged refresh strips the run's empty commits and carries the proof forward

```gherkin
Feature: Engine checkpoint commits never reach the merged history
  As a maintainer reading merged history
  I want a run's empty checkpoint commits dropped before publication
  So that only the work reaches the default branch

  Scenario: Empty commits are stripped under lease and the proof carries forward
    Given a published head that already contains the default branch and carries two of the run's empty commits
    When pr_refresh runs
    Then it republishes the head without the empty commits under an explicit lease on the run's publish branch
    And the proof decision is carried_forward because the tree is unchanged

  Scenario: A head with no empty commits is left alone
    Given a published head that already contains the default branch and carries none of the run's empty commits
    When pr_refresh runs
    Then it republishes nothing and the verified proof still names the published head
```

