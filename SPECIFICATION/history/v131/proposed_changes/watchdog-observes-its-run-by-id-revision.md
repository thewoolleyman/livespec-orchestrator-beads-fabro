---
proposal: watchdog-observes-its-run-by-id.md
decision: accept
revised_at: 2026-10-13T10:00:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under this repository's maintainer-armed delegated revise-decision mode (spec_governance.revise_decision_mode: delegated). The proposal fills the spec gap that refused bd-ib-6pdigz at dod_gate (run 01M4RM6ZFCHXQCFP3J35YWR5EM): v130's Dispatcher progress watchdog subsection governs what counts as progress and how a cancel routes, but not how the watchdog observes its run. The clause constrains only the observation mechanism after the run id is bound, preserves every verdict the watchdog reaches today, and makes a failed per-run read unobservable rather than a disappearance, so it cannot introduce a new false cancel. It contradicts no design record: the paragraph is additive to the v130 subsection and does not touch the progress rule, the cancel record or the cancel routing. Plan stall-watchdog-false-kills (epic bd-ib-laf735).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-13T09:59:53Z
verdict: NO BLOCKERS
proposal_stem: watchdog-observes-its-run-by-id
content_digest: 53e24c40722e470ed62cdeef8b771242a3f9a5abcf7a0d60e9646ab7cad12cc8
