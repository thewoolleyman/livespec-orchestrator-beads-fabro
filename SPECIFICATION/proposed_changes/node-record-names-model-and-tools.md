---
topic: node-record-names-model-and-tools
author: claude-opus-5-5
created_at: 2026-11-12T07:55:28Z
---

## Proposal: A node judgement record names the model it ran on and whether it could read the repository

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A judgement record names its taking, its digests and its outcome, but not the model that decided a node taking or what the node could read beyond the subject. So when a host taking admits an item the in-run `dod_gate` node then refuses, nothing on the ledger separates model variance from a difference in evidence, even once the two takings' subject digests can be compared. This proposal requires every judgement record to name its deciding agent and model and its evidence access, `subject-only` or `repository-tree`. It also requires each `dod-judgement-disagreement` row and record to carry both sides' values.

### Motivation

Slice 2 of bd-ib-8zyan, regroomed under plan bd-ib-ax3rds on 2026-11-12. legacy-coordinator-agent (session c29d86f8) approved the cut under coordinator-duties §5 and routed this slice as a propose-change for the coordinator's grade. It is not filed as an item. A dry `classified_candidate_slices` run put these two record fields at spec-change tier. The core node record and disagreement row are already stated by Scenario 240 and are carried by factory slice bd-ib-67wnts.

The defect it serves, measured on 2026-11-12. livespec-dev-tooling-n277mo: its pre-admission taking (2026-11-10 11:08Z) and its pre-dispatch taking (2026-11-12 05:48Z) were both decided by claude-acp claude-sonnet-5-5 and both ADMITTED. The `dod_gate` node of run 01M774XA07Q3 then refused on check 5 with the same four-name grading set, spending the run. The two host takings of n277mo graded DIFFERENT subject digests (65d8c69a… at pre-admission, then 831b4466… at pre-dispatch), and the node's digest is unrecorded until bd-ib-67wnts lands. So this instance does not by itself show a disagreement on identical bytes. livespec-dev-tooling-hlyayb was likewise a changed subject (484249d8… admitted at pre-admission, then c3171418… refused on check 4 at pre-dispatch), not the same bytes graded twice. The case for these fields rests on the next disagreement row being able to discriminate its cause, and that holds whatever these two instances turn out to have been. Once bd-ib-67wnts lands, a disagreement row will show whether the subject digests matched; identical digests already imply identical grading sets, because the subject carries the grading set. It still will not show WHY two takings of one rubric on one subject disagree. That leaves two candidate causes: (a) different models, since the node's model is an operator dial (`dispatcher.acp_nodes`) while host takings use the Dispatcher's selected credential; (b) different evidence. The node's check-5 finding cited repository inspection ("the path is absent in this sandbox", `livespec_dev_tooling/llm_spend.py:7`). A host taking grades the same subject bytes and reads no repository tree. Recording both values on every record makes the next disagreement row discriminate the two causes without a run dump.

This proposal records; it does not yet decide the remedy. Whether host takings should gain the tree, or the node should be confined to the subject, is a choice the recorded evidence should drive, and it is left for a later proposal.

In-flight alignment (survey 2026-11-12; relationship `align` for each): approve-refuses-on-a-proof (this seat, bd-ib-ccl3wf) adds pre-admission takings on more routes, and each will carry these fields like any host taking. #5013 the-filing-display-recognises-only, #5005 and #5009 do not touch the judgement record.

### Proposed Changes

**1. The record names its deciding model and its evidence access (`contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → §"Effective acceptance criteria" → "One rubric, one subject").**

After the sentence "Each record names the taking (and the run, for the node), the subject digest, the rubric digest, the outcome with any findings, and, for a chain, each candidate with its outcome." add:

> Every judgement record MUST also name the agent and model that decided it, in the `deciding-candidate` form host records already use (`<agent>:<model>`). For a node record, the Dispatcher MUST take that value from the agent and model the run resolved for its `dod_gate` node, and MUST NOT infer it from the node's output. Every judgement record MUST also carry an `evidence-access` field naming what the deciding judge could read besides its subject: `subject-only` for a judge given the subject and no repository tree, or `repository-tree` for a judge whose turn could read the governed repository's working tree. A host taking that hands its judge no tool able to read the repository records `subject-only`. A `dod_gate` node whose sandbox holds the run's checkout records `repository-tree`. A record whose deciding model or evidence access cannot be established MUST name that field `unobservable` with its cause, and MUST NOT omit it.

**2. A disagreement carries both sides' values (same paragraph, the opposite-outcomes sentence).**

Wherever the paragraph requires a `dod-judgement-disagreement` journal row and its item record for opposite outcomes on identical digests, each MUST also name, for each of the two takings, its deciding agent and model and its evidence access as its record states them. A row MUST NOT be withheld because either value is `unobservable`.

**3. Scenario (`scenarios.md`).** Append the following heading and gherkin block. The revise pass MUST give it the next free scenario number if 352 is taken, updating no other heading.

## Scenario 352 — A judgement record names its deciding model and evidence access, and a disagreement row carries both sides'

```gherkin
Feature: a host/node disagreement names the model and the evidence each side used
  Scenario: a node record names the node's model and repository-tree access
    Given a run whose dod_gate node resolved agent claude-acp and model <node-model>
    When the Dispatcher reads the run's dod_gate outcome
    Then the item's node judgement record names deciding-candidate claude-acp:<node-model>
    And the record names evidence-access repository-tree
  Scenario: a host record names subject-only access
    Given a pre-dispatch taking whose judge receives the subject and no repository tool
    When the taking appends its judgement record
    Then the record names its deciding candidate
    And the record names evidence-access subject-only
  Scenario: a disagreement row carries both sides' model and access
    Given an item whose pre-dispatch record admitted it and whose node record for a later run refused it on identical subject and rubric digests
    When the Dispatcher next reads the item's records
    Then the dod-judgement-disagreement row names each taking's deciding candidate and evidence access
  Scenario: an unobservable model is named, not dropped
    Given a run whose dod_gate node's resolved model cannot be established
    When the Dispatcher reads the run's dod_gate outcome
    Then the node record names deciding-candidate unobservable with its cause
```

**4. Revise co-edit.** `tests/heading-coverage.json` lies outside the spec target, so the revise CLI's `resulting_files[]` cannot carry it: the revise COMMIT that accepts this proposal MUST carry the edit itself. That commit MUST add one `tests/heading-coverage.json` row for the new heading, with `test: "TODO"`, `work_item: "bd-ib-5do354"` (the open implementing item, held at spec-change tier for this topic), and a non-empty `reason` naming the tier the owed test runs at, integration or above. The same commit MUST add one matching `tests/heading-coverage-debt.json` entry carrying the key three (`spec_root`, `spec_file`, `heading`), `work_item: "bd-ib-5do354"` and `first_seen` set to the revise date. That is the spec-first admission the `check-heading-coverage-debt-register` gate allows, so neither its `unregistered_todo` nor its `register_grew` direction fires. If the revise renumbers the scenario, the row and entry MUST carry the renumbered heading text.
