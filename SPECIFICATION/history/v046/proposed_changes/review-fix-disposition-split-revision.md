---
proposal: review-fix-disposition-split.md
decision: accept
revised_at: 2026-07-23T22:29:34Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Maintainer-directed restructure (2026-07-23, relayed via the thread supervisor): split finding-disposition out of the review fix stage. Design record plan/factory-success-rate-remediation/research/review-fix-split-design.md (bd-ib-o35rcx, child of epic bd-ib-cvgjop), independently adversarially reviewed (SOUND-WITH-CHANGES, both blocking findings incorporated). The proposal itself passed its own independent adversarial spec-ratification review with verdict NO-BLOCKERS (byte-exact anchors, no internal contradiction, faithful to the decided design); its two hardening advisories (single combined REPLACE; explicit at-least-one-accepted clause) were folded in before this accept. Selective revise: the two other pending proposals (reconcile-merged-dispatch-lock, wip-cap-zero-dispatch-off) belong to other threads and are deliberately left undecided this pass.

## Resulting Changes

- scenarios.md
- contracts.md
