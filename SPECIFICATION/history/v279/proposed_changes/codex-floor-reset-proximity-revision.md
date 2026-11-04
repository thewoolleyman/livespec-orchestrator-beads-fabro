---
proposal: codex-floor-reset-proximity.md
decision: accept
revised_at: 2026-11-02T20:54:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:plan-anthropic-burn-mitigation
---

## Decision and Rationale

Accepted under delegated revise_decision_mode. The maintainer approved this behaviour through coordinator ruling R301 (2026-11-02 ~19:3xZ): keep the Codex floor at 20% until about 12 hours before the weekly reset, then 5%. The change is scoped to the Codex usage-window clause, so the Claude clause and its floor are unchanged. It replaces the earlier 'a reset instant MUST NOT change any skip' rule with a per-window effective floor driven by the provider's reported reset_at. The scenarios cover both arms, the inclusive boundary, the under-5% refusal beside an unchanged Claude floor, and an absent reset_at. The independent sonnet review returned NO BLOCKERS on these exact bytes, rebased onto master after another revision took v278; master's contracts.md was unchanged and the scenarios insertion is byte-identical.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T20:54:12Z
verdict: NO BLOCKERS
proposal_stem: codex-floor-reset-proximity
content_digest: 593d2af1573303e35ac8af4982bf907eac4eea90ae77943ee99348a0920d6405
