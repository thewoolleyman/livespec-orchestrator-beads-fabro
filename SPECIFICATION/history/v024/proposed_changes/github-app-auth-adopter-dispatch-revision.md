---
proposal: github-app-auth-adopter-dispatch.md
decision: accept
revised_at: 2026-07-03T02:50:27Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Maintainer-ordered spec wave (overseer directive, 2026-07-03; the maintainer directive is the acceptance authority): codifies the five github-app-auth adopter-dogfood learnings as clause extensions to the Self-contained plugin dispatch contract — the full per-dispatch credential set with fail-closed target-wrapper-naming diagnostics, per-tenant engine App identity with an App-reach preflight and the workflows RW grant surfaced, the target-local workflow with target-toolchain prepare-step facts, and dispatch-path default-branch resolution. Architecture, not mechanism: implementation is cross-cited to the open ledger items (bd-ib-3m44nx, bd-ib-z2ctra, bd-ib-hkzcfb, bd-ib-ls32yb, bd-ib-umno37, bd-ib-w4iaaf), which implement to these clauses. Scenario 29 gains the diagnostic-content sub-scenario and new Scenario 32 covers the adopter-compatibility behaviors; the new H2 is co-registered in tests/heading-coverage.json in the same change.

## Resulting Changes

- contracts.md
- scenarios.md
