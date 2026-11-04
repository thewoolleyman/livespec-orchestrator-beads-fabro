---
proposal: reconcile-merged-pr-selector.md
decision: accept
revised_at: 2026-10-27T02:43:13Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed, spec-first for bd-ib-q3ejtp (coordinator gitops-fleet-capacity-monitoring ranks it normal-high; requested by petri-factory-on-gmktec; bd-ib-a3dzii folded in). A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) raised one blocker in each of three rounds, all folded in: janitor evidence for an item no factory run merged, that evidence bound to the selected pull request, and a refused reconciliation never replacing the host-record target. The fourth round returned NO BLOCKERS. The acknowledged tension with the pending proposal post-host-record-refuses-an-item-without-its-own-merged-pull-req is left for that proposal's own revision.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T02:42:22Z
verdict: NO BLOCKERS
proposal_stem: reconcile-merged-pr-selector
content_digest: b89c37be7cb563630e1dd7e769f8cd785e7c6200e5eed206aaffd541947e8f5e
