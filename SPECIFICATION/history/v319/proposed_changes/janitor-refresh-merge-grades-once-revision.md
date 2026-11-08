---
proposal: janitor-refresh-merge-grades-once.md
decision: accept
revised_at: 2026-11-08T02:43:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session a21903eb, claude-opus-5-5) under R301 delegated authority on 2026-11-08: ACCEPT on content digest 7b7ca682. A janitor refresh merge is created without committing and committed through the hooks, and a passing full pre-commit aggregate on exactly the merged tree is the visit's grading of it, so commit-time verification is kept and runs once. It conforms to livespec-dev-tooling's ratified suite-green Same-tree reuse bullet, whose implementation livespec-dev-tooling-z5fwwn owes. Basis: bd-ib-hap62u run 01M6VBZF4371, where a plain merge's commit-msg suite (1611.80 s) and the janitor's own aggregate together outran the 4340 s ceiling. Carried in the same pass as fix-turn-commits-run-the-affected-tests-gate.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T02:40:59Z
verdict: NO BLOCKERS
proposal_stem: janitor-refresh-merge-grades-once
content_digest: 7b7ca682b4e8032d65fa6d75109ab00db55efcef2051f30ede78c50c8980543d
