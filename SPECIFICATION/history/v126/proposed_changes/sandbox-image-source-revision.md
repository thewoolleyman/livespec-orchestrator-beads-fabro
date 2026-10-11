---
proposal: sandbox-image-source.md
decision: accept
revised_at: 2026-10-11T22:10:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal states a missing precedence rule measured on hp-candidate run 01M4PBFW4MP8, where the container ran the dispatcher.fabro_sandbox_image pin instead of the declared catalog environment image. It adds a BCP14 contract subsection under Dispatcher policy settings, Scenario 169 stating both precedence paths and the journaled image source, and the heading-coverage entry owned by bd-ib-jy7fuh.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-11T22:09:39Z
verdict: NO BLOCKERS
proposal_stem: sandbox-image-source
content_digest: 47df635db622ec638ea7e430ecc4b29dd96272fd2896d1eed44b1d8db04076d3
