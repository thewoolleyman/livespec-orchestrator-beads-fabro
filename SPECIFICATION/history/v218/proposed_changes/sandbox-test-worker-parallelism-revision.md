---
proposal: sandbox-test-worker-parallelism.md
decision: accept
revised_at: 2026-10-25T17:29:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Fleet coordinator ruling for bd-ib-yq4x4g, 2026-10-25: the factory's leading infra ending is a memory-cgroup OOM from gate runs sizing pytest-xdist workers to the node's 72 CPUs inside 4-CPU, 7630 MiB pods. This clause, a ### subsection of the existing H2 '## Dispatcher policy settings', governs the Dispatcher's bounded LIVESPEC_TEST_PARALLELISM projection; the implementation lands through the factory under bd-ib-yq4x4g.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T17:29:46Z
verdict: NO BLOCKERS
proposal_stem: sandbox-test-worker-parallelism
content_digest: e323ed5fd854625563042045b1627811ddf34aa6b2a1826987d789921e94e976
