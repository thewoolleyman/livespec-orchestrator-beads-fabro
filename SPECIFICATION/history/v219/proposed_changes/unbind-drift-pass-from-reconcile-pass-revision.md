---
proposal: unbind-drift-pass-from-reconcile-pass.md
decision: accept
revised_at: 2026-10-25T18:55:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Maintainer ruling 2026-10-25 (plan split-drift-check-from-cleanup-timer, bd-ib-oi2nyu): the cleanup job does cleanup only with no LLM spend, and the drift check is split into its own job that stays stopped until an operator enables it. Accepted verbatim; independent read-only Codex review returned NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T18:53:57Z
verdict: NO BLOCKERS
proposal_stem: unbind-drift-pass-from-reconcile-pass
content_digest: 855824c0325b60c28b0a7647e212ee8ecb38beccca511d0141f9828ba32fb6ac
