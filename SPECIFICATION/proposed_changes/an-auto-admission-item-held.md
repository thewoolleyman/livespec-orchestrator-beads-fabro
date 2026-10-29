---
topic: an-auto-admission-item-held
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T09:43:49Z
---

## Proposal: approve re-runs the intake Definition-of-Done check for an auto-admission item held at pending-approval

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under ## Work-item state semantics, extend the approve door so an item whose effective admission policy is auto, and which intake held at pending-approval on a mechanical Definition-of-Done finding, is released by approve when a fresh run of the intake Definition-of-Done check reports no mechanical finding, and refused with the finding recorded when it still does.

### Motivation

Work-item bd-ib-idpr32 measures a stranded state. Intake routes an auto-admission item whose Definition of Done carries a mechanical finding to pending-approval, but once the description is repaired nothing re-evaluates it: approve refuses because the item is not effective-manual, next never lists a pending-approval item, and the pending-approval to ready move was removed as an unjournaled duplicate of approve. Measured on bd-ib-ssmioz on 2026-10-22, whose Definition-of-Done preflight passed on both legs while drive approve refused with invalid-source-state. The orchestrator's spec-change-tier gate held idpr32 on 2026-10-29 (topic an-auto-admission-item-held) because the ratified text names approve as the single door from pending-approval toward ready, limits approve to effective-manual items, and states no release-or-refuse behaviour for this case. Extending approve keeps approve the single journaled door instead of adding a second verb, and it covers the related bd-ib-lijsh5 case (an item flipped to auto by set-admission and stranded at pending-approval), because the rule keys on the item's current state and effective policy rather than on how it got there.

### Proposed Changes

In SPECIFICATION/contracts.md, under ## Work-item state semantics, after the paragraph that begins '**`approve` IS the `pending-approval → ready` transition**', add:

**`approve` on an auto-admission item held by intake.** For an item in `pending-approval` whose EFFECTIVE `admission_policy` is `auto`, `approve` MUST re-run the intake Definition-of-Done check against the item's current text before deciding. When that check reports no mechanical finding, `approve` MUST move the item to `ready`, journaled with its actor like any other approval. When it still reports a mechanical finding, `approve` MUST leave the item in `pending-approval`, MUST refuse with a result naming each mechanical finding, and MUST record those findings on the item as a ledger comment. Advisory findings MUST NOT block the release. `approve` on an effective-manual item is unchanged. This keeps `approve` the single journaled door from `pending-approval` toward `ready`; no second verb is added.

In the per-lane valid operator verb sets table, change the `pending-approval` row's first entry from 'approve (the single door toward `ready`)' to 'approve (the single door toward `ready`; for an effective-auto item it re-runs the intake Definition-of-Done check first)'.

In SPECIFICATION/scenarios.md, append:

## Scenario 259 — approve releases an auto-admission item whose repaired Definition of Done now passes, and refuses one that still fails

Given a work-item in `pending-approval` whose effective `admission_policy` is `auto`, held there by intake on a mechanical Definition-of-Done finding

And its description has since been repaired so the intake Definition-of-Done check reports no mechanical finding

When the operator drives `approve:<id>`

Then the item moves to `ready` and the transition is journaled with its actor

Scenario: an auto-admission item whose Definition of Done still fails stays held

Given a work-item in `pending-approval` whose effective `admission_policy` is `auto`, whose description still carries a mechanical Definition-of-Done finding

When the operator drives `approve:<id>`

Then the item stays in `pending-approval`

And the result names the mechanical finding

And the finding is recorded on the item as a ledger comment

The revise that accepts this proposal MUST add a tests/heading-coverage.json entry for the new Scenario 259 heading, with test "TODO" and a reason naming bd-ib-idpr32 as the implementing item.
