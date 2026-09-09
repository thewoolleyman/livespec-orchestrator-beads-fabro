---
proposal: adopt-native-open-assigns-rank.md
decision: accept
revised_at: 2026-09-09T11:37:48Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-agent-sdk
---

## Decision and Rationale

Ratifies an existing, verified Dispatcher self-heal (open->backlog, in_progress->active) already implemented in _dispatcher_ledger_close.py, closing impl->spec drift per this repo's mutation discipline, and adds one new normative requirement (assign a real non-sentinel rank on adoption) that is directly implied by the already-ratified 'every live head issue has a real, non-sentinel rank' invariant this repo's own Invariants block states. No design-record contradiction, no ambiguity, no open sub-decision.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: manual-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-09T11:36:47Z
verdict: NO BLOCKERS
proposal_stem: adopt-native-open-assigns-rank
content_digest: be14ae52df8a90d373a43d8b3093023c28c04e73e8dcdfc9a285442aed19a6c4
