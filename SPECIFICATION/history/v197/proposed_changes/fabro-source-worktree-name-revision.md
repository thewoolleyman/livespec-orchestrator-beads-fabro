---
proposal: fabro-source-worktree-name.md
decision: accept
revised_at: 2026-10-22T01:20:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Coordinator R541 asked for this ratification and R202 authorizes this seat to revise it. The proposal states, without changing behaviour, the worktree path fabro-source-<id> and the branch livespec/source/<id> that _dispatcher_source_staging.py already mints, so livespec-dev-tooling's v083 reap-safety clause, which identifies factory-owned worktrees by that name, rests on a ratified interface rather than an implementation detail. No design record is contradicted: the names were never ratified before, and the clause only constrains the existing staging, adding no step to the closed step set. Scenario 236 states the behaviour; its heading-coverage TODO and debt entries are owned by bd-ib-7pags, which adds the exact-name test. Independent read-only gpt-6-astra review of the exact resulting bytes returned NO BLOCKERS. Step 3.5 was run with --skip-stale-branch-check after verification: it flagged this revise's own proposal commit on spec/fabro-source-worktree-name, and spec/reprove-merged-item-v2, another thread's branch whose only change is SPECIFICATION/proposed_changes/reprove-merged-item.md and which touches neither file this revise edits.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T01:19:44Z
verdict: NO BLOCKERS
proposal_stem: fabro-source-worktree-name
content_digest: 5714725aebd92ca0d9a508bd5dd03feace30ac4ce88597fd48ca2d81e03aba48
