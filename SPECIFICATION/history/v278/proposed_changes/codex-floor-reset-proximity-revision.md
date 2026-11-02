---
proposal: codex-floor-reset-proximity.md
decision: accept
revised_at: 2026-11-02T19:34:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:plan-anthropic-burn-mitigation
---

## Decision and Rationale

Accepted under delegated revise_decision_mode. The maintainer approved this behaviour through coordinator ruling R301 (2026-11-02 ~19:3xZ): keep the Codex floor at 20% until about 12 hours before the weekly reset, then 5%. The change is scoped to the Codex usage-window clause, so the Claude clause and its floor are unchanged. It replaces the earlier 'a reset instant MUST NOT change any skip' rule with a per-window effective floor driven by the provider's reported reset_at. The scenarios cover both arms, the inclusive boundary, the under-5% refusal beside an unchanged Claude floor, and an absent reset_at. The independent sonnet review returned NO BLOCKERS on these exact bytes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T19:34:01Z
verdict: NO BLOCKERS
proposal_stem: codex-floor-reset-proximity
content_digest: 6faf541b984f1c9b6e01a45b6f2fc752fd2f414f835b4d521a271fefd0da86c5
