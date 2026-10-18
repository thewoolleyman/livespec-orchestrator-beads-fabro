---
proposal: fix-turn-suite-once.md
decision: modify
revised_at: 2026-10-18T11:31:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session sandbox-commit-gate-ceiling under the delegated authority of driver gitops-fleet-capacity-monitoring ruling R168 (bd-ib-k6dwyv admitted as an R34-class root-cause fix). The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on these final bytes after a first pass whose single blocker the modification resolves.

## Modifications

One revise-time modification, from the configured reviewer's first-pass blocker: the paragraph is scoped to a fix turn that completes successfully and routes to janitor, and leaves needs-human, node-timeout and other failure exits under their existing handling (contracts 'A factory run never awaits a human' and 'A commit run outlives a node-timeout cut'); Scenario 199's When steps say 'completes successfully'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T11:31:03Z
verdict: NO BLOCKERS
proposal_stem: fix-turn-suite-once
content_digest: 0a9851079373017dd0f3b98aa0faff6ab14fca82cb84df0270e39081c199b5bf
