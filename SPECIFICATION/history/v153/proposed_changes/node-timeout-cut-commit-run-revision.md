---
proposal: node-timeout-cut-commit-run.md
decision: modify
revised_at: 2026-10-18T01:49:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session sandbox-commit-gate-ceiling under the delegated authority of driver gitops-fleet-capacity-monitoring rulings R132 and R133 (bd-ib-ptnxyg admitted as an R34-class root-cause fix). The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on these final bytes after a first pass whose two blockers the modification resolves.

## Modifications

Two revise-time modifications, both from the configured reviewer's first-pass blockers. (1) The passed-commit history requirement is scoped to the commit run that was running at the cut, and states that a commit the agent itself superseded (a Red commit replaced by a Green amend) need not remain in the preserved history; Scenario 192's first Then names that commit run's resulting HEAD commit. (2) The bounded wait ends while enough of the needs_human node's timeout remains for a bounded preservation attempt, and preservation proceeds per 'A factory run never awaits a human', by a pushed ref or, when the push does not complete, the preserve-by-reference pointer.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T01:49:36Z
verdict: NO BLOCKERS
proposal_stem: node-timeout-cut-commit-run
content_digest: 87ead6e3dc15ed4c3f33c19fbb4576f6951b903a940cdf7251ea317e9e9c3618
