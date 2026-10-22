---
proposal: dod-judgement-verdict-binding.md
decision: accept
revised_at: 2026-10-22T10:19:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which filed the proposal (PR 3505) as the follow-up to v201 that coordinator R595b asked for. A taking is one invocation of the Definition-of-Done judgement. Every taking records one judgement record, and those records are excluded from the subject. The earliest completed host verdict on identical subject and rubric digests binds every later host taking without running a judge. Did-not-run, node and disagreement records never bind, and a candidate that cannot run makes the preflight a did-not-run, never a refusal. The node still runs on every run and its outcome is recorded. Opposite outcomes on identical digests, between any two takings or two candidates of one chain, are journaled once as dod-judgement-disagreement. Measured motivation: one judge flipping on unchanged input (Evidence 5 on livespec-dev-tooling-ggoyiq, Evidence 6 on bd-ib-gob6gl). It departs from no design record; the node's every-run duty is retained. The implementing work-item bd-ib-8zyan (blocked by bd-ib-gob6gl) owns Scenario 240's coverage TODO. The configured ratification reviewer, gpt-6-astra, in a separate read-only Codex session, returned NO BLOCKERS on round 3 of the proposal text and NO BLOCKERS on the exact resulting bytes (digest ee86c789eca0135d2cf92f649346249426057c90c1481679e7f304bb7a93e6aa), which it recomputed independently.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T10:18:46Z
verdict: NO BLOCKERS
proposal_stem: dod-judgement-verdict-binding
content_digest: ee86c789eca0135d2cf92f649346249426057c90c1481679e7f304bb7a93e6aa
