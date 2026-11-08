---
proposal: dispatch-terminal-span-scheduler-inputs.md
decision: modify
revised_at: 2026-11-04T21:04:47Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:radar-and-deterministic-admission
---

## Decision and Rationale

Decided in delegated mode by claude:radar-and-deterministic-admission. legacy-coordinator-agent accepted this proposal under ruling R301 (2026-11-04) on the maintainer's behalf. It carries plan assertions 9 and 10 of livespec-dev-tooling plan radar-and-deterministic-admission (epic livespec-dev-tooling-w7ley3). The terminal dispatch span gains the four cost attributes the radar admission function reads: run class, execution target, sandbox CPU-seconds and peak memory. Under coordinator ruling R301 (2026-11-02) this extends bd-ib-welwbc's span and adds no parallel span. A just-check member reads livespec-dev-tooling's required_columns.json from the pinned package, so a dropped or renamed attribute cannot silently starve the scheduler. The implementation items are bd-ib-faprof (blocked by bd-ib-welwbc) and bd-ib-atmome (blocked by bd-ib-faprof, and across tenants by livespec-dev-tooling-k3dpo2 and a pin bump).

## Modifications

Four changes against the proposal text. First, the scenarios are numbered 310 and 311, not 309 and 310, because v298 took Scenario 309 while this proposal waited. Second, the four attributes form a new paragraph, 'Terminal-span cost attributes', placed directly after the terminal-span paragraph. The proposal inserted them in the middle of that paragraph, which would have split it with a list. The omit-and-name sentence now reads 'every other value of the terminal span' to fit the new placement. Third, both scenarios carry a 'Governing clause:' line, as recent scenarios do, and their Then-lines use the surrounding gherkin's plain present tense. Fourth, the heading-coverage TODO rows for Scenarios 310 and 311 (integration tier, owned by bd-ib-faprof and bd-ib-atmome) and their debt-register entries are co-edited in the revise commit. The independent review of the final bytes found NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T21:04:30Z
verdict: NO BLOCKERS
proposal_stem: dispatch-terminal-span-scheduler-inputs
content_digest: 21f7868a91e86157019f89d758a575f1d78fa5c302f23765ae20af12592ad11c
