---
proposal: the-reconcile-runs-host-timer.md
decision: accept
revised_at: 2026-11-14T07:26:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision as a single-topic pass (--only-topic), accepted as written on legacy-coordinator-agent's order, relayed by legacy-dispatcher-agent. It releases bd-ib-cwuxfi (the reconcile-runs host timer re-parses each dispatch journal many times per pass) from its spec-change-tier hold. The new "Reconciliation-pass reads" paragraph lands in contracts.md §"Bounded Fabro event reads" directly after "Pre-launch reads" and before the Scenario 227 pointer line, so the dispatch pass and the standalone reconcile-runs pass state one principle; the four new scenarios land inside Scenario 227 after "Each loop pass reads afresh" and before "Concurrent reads are capped across processes on one host". No H2 heading changes, so tests/heading-coverage.json needs no co-edit. Every other pending proposal stays in place. This version is cut on PR #5213's head (v374) and is rebased onto master when #5213 merges.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T07:26:07Z
verdict: NO BLOCKERS
proposal_stem: the-reconcile-runs-host-timer
content_digest: abeb4ae25d7972d69ec6c2774502bf321d9aee5d518472c7d54e52b7e65e369e
