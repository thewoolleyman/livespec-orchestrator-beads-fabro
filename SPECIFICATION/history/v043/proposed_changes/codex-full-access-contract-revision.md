---
proposal: codex-full-access-contract.md
decision: accept
revised_at: 2026-07-19T18:36:34Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Ratifies the manifest-gated Codex full-access contract now that the whole implementation has shipped and been verified (S1 #782, S2 #791, S3 #800, C1 #803, plus defect fixes #793/#795 and the fail-closed hardening). The proposal text was amended before ratification so it describes the system AS BUILT: adversarial Codex review of the pre-implementation draft against the shipped code returned four blocking discrepancies, each independently verified at file:line. Most severe: the draft required a canary that checks the source 'contains the expected sentinel', which IS the defect PR #795 fixed — ratifying it would have written a known-bad implementation into the spec as a requirement. Also corrected: a raw-exec bullet that contradicted the manifest gate, an identity-resolution claim describing gate-time behavior that does not exist (making a Scenario 21 Given unverifiable), and an instruction that would have deleted a real bound test from heading-coverage. The two-copy hook duplication is recorded as a known gap tracked by bd-ib-1jye.6 rather than blessed.

## Resulting Changes

- constraints.md
- scenarios.md
