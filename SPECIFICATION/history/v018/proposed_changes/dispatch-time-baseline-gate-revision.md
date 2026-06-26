---
proposal: dispatch-time-baseline-gate.md
decision: accept
revised_at: 2026-06-26T19:02:40Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted: codifies the Conformance Pattern dispatch-time tier (livespec-zs22.7.7 M6-f) as a new contracts.md H2, parallel to the Planning Lane and grooming realizations. Augmentation contract (no new gap-detectable clause, no new ledger state) over the existing Fabro prepare chain, which gains the two baseline Verifier prepare steps in the same change. heading-coverage.json co-edited for the new H2.

## Resulting Changes

- contracts.md
- ../tests/heading-coverage.json
