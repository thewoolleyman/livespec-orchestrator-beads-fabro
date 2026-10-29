---
topic: an-item-whose-factory-captured
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T14:09:20Z
---

## Proposal: A complete implement turn with no diff ends as already satisfied, not as a dead implementer

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under ## Self-contained plugin dispatch, a run whose implement turn reports the Definition of Done complete with an unchanged tree ends with a distinct already-satisfied outcome, releases its claim, and rests the item in acceptance with needs-attention naming the route to its Proof of Done; an incomplete turn with no diff is still a dead implementer.

### Motivation

Work-item bd-ib-mvws23 measures a dispatch outcome that today reads exactly like a failed attempt. When an item's factory_captured assertions are already true on the default branch, the implementer correctly reports the Definition of Done complete and changes nothing, and the run then ends at dead_implementer ('unchanged tree after implementer'), so proof_capture and proof_verify are never reached and the item is left active with a stranded factory claim. Measured instances: ob-5qlusq (openbrain, run 01M5KH0RTEDCCY634QWQMPHYH1, 2026-10-23), closed by hand as absorbed; and bd-ib-aty2ay (run 01M63GQPDBZZJ165PQ8RR56KQY, 2026-10-29), whose work had merged as PR 3749 two days earlier and which needed a hand reconcile and two host replays to close. The orchestrator's spec-change-tier gate held mvws23 on 2026-10-29 (topic an-item-whose-factory-captured) because the ratified text decides the implement outcome from the completion field and fails an incomplete turn, but states nothing about a complete turn with no diff or about a resting state that names a route to Proof of Done for such an item.

### Proposed Changes

In SPECIFICATION/contracts.md, under ## Self-contained plugin dispatch, after the paragraph that begins '**An implement turn that ends incomplete does not succeed.**', add:

**An implement turn that reports completion with no diff ends as already satisfied.** When the `implement` turn's structured completion field reports the Definition of Done complete and the run's tree is unchanged against the dispatch base, the run MUST NOT end at the generic dead-implementer truncation. It MUST end with an already-satisfied outcome that names the item and the dispatch base, and it MUST journal that outcome distinctly from a dead-implementer truncation. After that outcome the Dispatcher MUST release the run's factory claim and MUST rest the item in `acceptance`, where `needs-attention` surfaces it with the route by which its Proof of Done can still be obtained: `reconcile-merged` when a merged pull request for the item exists, and otherwise a proof-only run against the dispatch base. A turn that reports the Definition of Done incomplete with an unchanged tree still ends at `dead_implementer` with today's truncation record.

In SPECIFICATION/scenarios.md, append one scenario (numbered at revise):

## Scenario NNN — A complete implement turn with no diff ends as already satisfied, not as a dead implementer

Given a work-item whose factory_captured assertions are already true on the default branch

When its dispatch's `implement` turn reports the Definition of Done complete and the run's tree is unchanged against the dispatch base

Then the run ends with an already-satisfied outcome naming the item, not at `dead_implementer`

And the item rests in `acceptance` with no stranded factory claim, and `needs-attention` names the route to its Proof of Done

Scenario: an incomplete implement turn with no diff is still a dead implementer

Given a dispatch whose `implement` turn reports the Definition of Done incomplete and leaves the tree unchanged

When the run evaluates the implementer's outcome

Then the run ends at `dead_implementer` with today's truncation record

The revise that accepts this proposal MUST add a tests/heading-coverage.json entry for the new scenario heading, with test "TODO" and a reason naming bd-ib-mvws23 as the implementing item.
