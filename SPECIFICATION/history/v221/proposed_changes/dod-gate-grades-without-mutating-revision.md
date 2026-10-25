---
proposal: dod-gate-grades-without-mutating.md
decision: modify
revised_at: 2026-10-25T20:56:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The dod_gate clause said what the node must verify but not that it may not change the tree; run 01M5SWSTWJZB (bd-ib-nz4av6) showed a Codex dod_gate turn implementing the item for two 30-minute turns. Ratifying the no-mutation boundary gives the implementing item bd-ib-al54tl a heading to cite. Routing reuses the existing outcome=failed Blocked edge, so no edge, transition or exit code is added.

## Modifications

Per the independent ratification review's two blockers: (1) the non-mutating scenario now requires a coherent Definition of Done with no Definition-of-Done finding before it proceeds to implement, so an incoherent item graded without mutation still fails per Scenario 131; (2) a third sub-scenario asserts that the rendered dod_gate prompt states the boundary, including the prohibition on running the repository's declared check suite. The contracts.md sentences are unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T20:56:20Z
verdict: NO BLOCKERS
proposal_stem: dod-gate-grades-without-mutating
content_digest: a92c5139ea45538b1a0d0c968318c08dd0d283964c3baf0b49166b9c01bc9d18
