---
proposal: admission-session-headroom.md
decision: accept
revised_at: 2026-10-14T05:13:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-spec-session-headroom
---

## Decision and Rationale

Implements the Definition of Done of bd-ib-jwuxs4, adopted by plan factory-configurable-model-fallback-priority under the maintainer's 2026-10-14 ruling that it owns provider session-limit handling. An independent Codex gpt-6-astra review returned ACCEPT-WITH-CHANGES; every required change (covered-candidate definition on resolved agent provenance and credential projection, disabled-floor precedence, the eligibility predicate, containment-refusal and admission-wait registration, determinate scenarios) is folded in, and its second pass returned NO BLOCKERS, after master reverted v133 a third pass returned NO BLOCKERS, and after master ratified v133 (whole-run wall budget) and v134 (refresh repair, hook limits) a fourth pass returned NO BLOCKERS on these rebased exact bytes, finding no conflict with either.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-14T05:12:47Z
verdict: NO BLOCKERS
proposal_stem: admission-session-headroom
content_digest: 679722129064338c4d59e455262239b2d6d7cfd11048fec5d564ca33f210ff62
