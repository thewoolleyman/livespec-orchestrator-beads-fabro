---
proposal: implement-gate-preview-and-mechanical-budget.md
decision: accept
revised_at: 2026-11-03T15:50:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted verbatim under delegated revise mode, on the maintainer's 2026-11-03T15:00:49Z ruling recorded on livespec-dev-tooling-6tgd2z ('do them asap, they are a big lever'), assigned to plan sandbox-commit-gate-ceiling (epic bd-ib-qy5wol). Evidence: crxcy4 (01M6GVFTX08S), d2qm5d (01M6GQFBQTTJ) and jzwgjw each ended LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED after a full 1 to 2 h run. Independent read-only sonnet review of the final bytes: NO BLOCKERS. Non-blocking notes carried for the implementing items bd-ib-cwnt3b and bd-ib-v5dqyn: (1) the engine visit bound is the sum of the ordinary and mechanical budgets, which the new paragraph's last sentence requires; (2) the green prompt's 'run only the tests its change touches' and the gate preview's full hook checks are distinct duties and both stand; (3) the preview-absent, no-target, default-value and visit-bound cases are carried by the paragraph text without a dedicated scenario.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T15:48:56Z
verdict: NO BLOCKERS
proposal_stem: implement-gate-preview-and-mechanical-budget
content_digest: 4d5ef0f836456cad2049a5900a0d40920afc61947d8b0b455d6891d76c84612a
