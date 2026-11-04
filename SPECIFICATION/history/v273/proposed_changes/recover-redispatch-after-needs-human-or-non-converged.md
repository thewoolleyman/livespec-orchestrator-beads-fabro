---
topic: recover-redispatch-after-needs-human-or-non-converged
author: claude-opus-5-5
created_at: 2026-11-02T01:00:31Z
---

## Proposal: Recovery routing covers an item returned to ready after a needs_human or non_converged ending

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen 'released for recovery' in contracts.md 'Recovery from the failed run's preserved work' so that an item whose latest dispatch ended at the needs_human or non_converged terminal, and which has since returned to ready with no newer dispatch, is graded by recovery routing like every other released item. That means resume at the anchored node when a published head and a proof record satisfy the resume preconditions, and seeded from its preserved work otherwise. Today such an item is routed fresh: its publish branch is parked under refs/livespec/preserved-publish and deleted, and the new run starts from the default branch and goes through dod_gate and implement again. The change consumes no rework-cap budget, and the across-dispatch no-progress refusal still takes precedence. Scenario 296 states the behavior.

### Motivation

Measured by livespec-dev-tooling plan codex-implement-cost-per-run (epic livespec-dev-tooling-vspttc), research 002 and 003, over Honeycomb llm-spend and fabro, 7 days ending 2026-11-02. 237 Codex implement dispatches cost $2,672.65. Re-dispatches of an item already dispatched once cost $855.32 (32%), and dispatches that ended without a merge and were later re-dispatched cost $1,240.12 (46%). 48 of the 89 re-dispatches followed a dispatch whose implement node ended ok, so the failure came at a later node (review, proof, dod_gate, publish). Those items were routed fresh under the current text, and each re-ran implement from scratch on the full brief. UPPER BOUND on the work this change removes: $379.45 of Codex implement spend per 7 days for those 48 re-dispatches, which a resume skips entirely. Part of the $475.87 spent on the 41 re-dispatches after an errored implement is also in reach, where a seeded start keeps the Red commit and staged work. The realized share depends on how many such items carry a published head and a proof record. The hold half of the same lever (dispatcher.redispatch_no_progress_limit, 'Across-dispatch required-result progress') is already ratified and is carried by bd-ib-s5idxj; this proposal does not restate it. Routed by the coordinator legacy-coordinator-agent on 2026-11-02; no orchestrator plan owns re-dispatch recovery. In-flight survey: no open spec-touching pull request; pending proposal transient-infra-release-and-re-dispatch adds a release route to the same section and is compatible (align).

### Proposed Changes

In SPECIFICATION/contracts.md, under "## Factory-configurable ACP fallback priority", in the **Recovery from the failed run's preserved work.** paragraph, immediately after the sentence that ends "...while it is a stale assignee whose run stamp names a run (§\"Stranded claim release\" → \"Stale assignee clearance\")." insert:

> An item is also released for recovery when its latest journaled dispatch ended at the workflow's `needs_human` terminal or at a `non_converged` terminal, the item has since returned to `ready` by any path (a human valve, a groom, or a return from `backlog`), and no newer dispatch has been submitted for it. Such an item MUST be graded by recovery routing exactly as every other released candidate is: it MUST be routed `resume` at the anchored node when every precondition of §"Resume from a published pull request (`resume --item`)" passes, `seeded` from its preserved work when every applicable resume refusal is fallback-permitting and preserved work is verified, `fresh` only when preserved work is confirmed absent, and `held` when a non-fallback refusal applies or a measurement routing needs cannot be taken. Its preserved work MUST be taken in the preference order this paragraph already states, so the pushed ref a needs-human ending preserves under §"A factory run never awaits a human", and the preservation ref of a failed engine checkpoint, are preferred over the observed published head. A Definition of Done changed by a groom while the item rested is the existing fallback-permitting refusal, so the item MUST be seeded and MUST NOT inherit proof from the earlier Definition of Done. This release MUST NOT consume any budget of §"The three rework caps", and MUST NOT change how §"Across-dispatch required-result progress" counts the dispatch that ended it: that section's pre-claim refusal is graded before admission, and an item it refuses MUST NOT be offered to recovery routing in that pass. The goal brief of a `resume` or `seeded` dispatch of such an item SHOULD name the terminal it recovers from and the needs-human or non-convergence cause recorded on the item.

The sentence "An item not released for recovery is routed `fresh` without any remote measurement." MUST remain unchanged; after this change it no longer covers an item whose latest dispatch ended `needs_human` or `non_converged`.

In SPECIFICATION/scenarios.md, append:

```markdown
## Scenario 296 — An item returned to ready after a needs-human or non-converged ending is re-dispatched from its preserved work

Feature: Recovery routing covers an item returned to ready after needs_human or non_converged
  As the factory operator
  I want a re-dispatch of an item whose last run ended needs_human or non_converged to continue from that run's preserved work
  So that the factory does not re-derive implement work it already did

  Scenario: A returned item with a published head and a proof record is resumed at the anchored node
    Given item "W" whose latest dispatch ended at the needs_human terminal after proof_capture posted a captured proof record naming the published head
    And a human valve returned "W" to ready with its Definition of Done unchanged and no newer dispatch submitted
    When the Dispatcher's next pass grades "W"
    Then recovery routing routes "W" resume
    And the resumed run enters at review on the anchored head without visiting dod_gate or implement

  Scenario: A returned item with preserved work and no proof anchor is seeded
    Given item "W" whose latest dispatch ended at a non_converged terminal with a preserved terminal tree and no proof record
    And "W" returned from backlog to ready with no newer dispatch submitted
    When the Dispatcher's next pass grades "W"
    Then recovery routing routes "W" seeded
    And the seed record names the source run and the preserved tree's commit SHA and preservation reference
    And the new sandbox checks out that recorded SHA

  Scenario: A groomed Definition of Done falls back to a seeded dispatch
    Given item "W" whose latest dispatch ended at the needs_human terminal with a published head and a verified proof record
    And a groom changed the Definition of Done of "W" before it returned to ready
    When the Dispatcher's next pass grades "W"
    Then recovery routing routes "W" seeded
    And no proof record from the earlier Definition of Done is inherited

  Scenario: The across-dispatch no-progress refusal takes precedence over recovery routing
    Given item "W" whose latest dispatch ended at the needs_human terminal and returned to ready
    And the across-dispatch required-result progress refusal applies to "W"
    When the Dispatcher's next pass grades "W"
    Then the refusal is recorded before any claim
    And "W" is not offered to recovery routing in that pass
```

The co-edit of tests/heading-coverage.json for the new scenario heading lands in the revise commit, not in this proposal.
