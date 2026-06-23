---
proposal: provider-subscription-worker-credential-projection.md
decision: accept
revised_at: 2026-06-23T00:40:15Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted as filed. Codifies the provider-agnostic worker credential-projection invariant (non-rotatable-by-worker + Dispatcher freshness-gate + host sole-refresh-owner), de-risked by empirical verification that the Codex ACP path self-refreshes via codex-core's AuthManager and tolerates a non-rotatable projected snapshot. Adds Scenarios 18-19 and their heading-coverage entries; the proposal's 7 declared impl_followups are the realization plan, filed into the ledger separately.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
