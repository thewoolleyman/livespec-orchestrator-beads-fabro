---
topic: a-work-item-rider-reaches
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T14:27:41Z
---

## Proposal: Work-item riders are scoped to the stages they name, and an unscoped rider reaches only the tree-changing stages

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under ## Dispatch-brief lessons injection, a rider may name its stages on its first line; each stage's goal brief carries only riders naming that stage, and a rider naming no stage reaches only implement and review_fix, never review, proof_capture or proof_verify.

### Motivation

Work-item bd-ib-rczglr measures that every ledger comment on an item is rendered into ONE goal brief that every stage receives (`_dispatcher_goal.py` collects them as riders with no per-stage targeting). An implement-directed rider therefore also instructs review and proof turns. Measured on petri on 2026-10-26: bd-ib-ytrpb5 run 01M5WJK5R48W and bd-ib-atyefi run 01M5WKT1X4YP each had review@2 emit no verdict and narrate an implement turn, following their implement-directed riders; the coordinator attributed two terra crossings to this leak (ruling R55). The maintainer asked for the remedy to be mechanically linked and fail-safe. Since then this seat has stage-scoped every rider by hand ('FOR implement and review_fix ONLY: ...'), which works only while every author remembers to. The orchestrator's spec-change-tier gate held rczglr on 2026-10-29 (topic a-work-item-rider-reaches) because the ratified text states no per-stage scoping of riders, and named ## Dispatch-brief lessons injection, the clause governing brief composition, as the heading to generalize. The fail-safe default for an unscoped rider is the tree-changing stages, so a rider can never instruct a grading stage unless it says so.

### Proposed Changes

In SPECIFICATION/contracts.md, at the end of ## Dispatch-brief lessons injection, add:

**Work-item riders are scoped to the stages they name.** A rider is a ledger comment on the work item that the Dispatcher renders into a stage's goal brief as operator instruction. A rider MAY name the stages it applies to on its own first line, in the form `FOR <stage>[, <stage>...] ONLY:`, using the workflow's stage names. The goal brief the Dispatcher renders for a stage MUST carry each rider that names that stage, and MUST NOT carry a rider that names only other stages. A rider that names no stage MUST reach only the `implement` and `review_fix` stages' briefs, because those are the stages that change the tree; it MUST NOT reach the `review`, `proof_capture` or `proof_verify` briefs. Ledger comments that are records rather than instructions, such as Definition-of-Done judgement records, remain excluded from every brief as they are today.

In SPECIFICATION/scenarios.md, append one scenario (numbered at revise):

## Scenario NNN — A work-item rider reaches only the stages it names

Given a work item carrying a rider whose first line is `FOR implement ONLY:`

When the Dispatcher renders the goal briefs for its run

Then the implement brief carries that rider

And the review, proof_capture and proof_verify briefs do not

Scenario: a rider that names no stage reaches only the tree-changing stages

Given a work item carrying a rider that names no stage

When the Dispatcher renders the goal briefs for its run

Then the implement and review_fix briefs carry that rider

And the review, proof_capture and proof_verify briefs do not

The revise that accepts this proposal MUST add a tests/heading-coverage.json entry for the new scenario heading, with test "TODO" and a reason naming bd-ib-rczglr as the implementing item.
