---
proposal: sandbox-image-enumeration.md
decision: modify
revised_at: 2026-10-20T16:50:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fabro-currency (session 5c3e43cb)
---

## Decision and Rationale

Accepted with modification under this repository's delegated revise_decision_mode, by session fabro-currency, routed by fleet coordinator gitops-fleet-capacity-monitoring as R295/R296 for work-item bd-ib-nqmltq, whose first dispatch's pre-dispatch preflight found three ungoverned behaviours: the repository set, the executing-build set and the unreadable source. The subsection governs a read-only dispatcher.py sandbox-images primitive that the docker factory host image-warm timer of livespec-dev-tooling-dq3km7 consumes, so that two first pulls of one new tag cannot race on a host (hold R286). It answers through the dispatch's own resolvers and changes no dispatch behaviour. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 2. The Step 3.5 stale-branch precondition was skipped with --skip-stale-branch-check: its findings are other sessions' unlanded proposal branches that touch neither changed section.

## Modifications

Three repairs from ratification-review round 1. (1) Scope: the enumeration covers every dispatch without an explicit --workflow path, using the command process's own environment. It adds one named_variant entry per variant declared under dispatcher.workflows, because the ratified 'Named workflow variants' paragraph puts a selected variant ahead of the reserved workflow and the warm timer must hold every tag an ordinary dispatch can pull. The configured-image arm names the dispatch resolver's environment-first order (LIVESPEC_FABRO_SANDBOX_IMAGE before dispatcher.fabro_sandbox_image), and the reserved arms are renamed committed_run_config and bundled_run_config. The reviewer had suggested narrowing to the reserved workflow; this alternative was taken deliberately and accepted in round 2. (2) A dead-process lease contributes no build, but a build reached by another route is still enumerated, which removes an include/exclude contradiction. (3) Scenario 212 gains the reviewer's cases for default discovery, explicit --repo, an undeclared factory exiting zero, the deduplicated host-wide build union, resolver reuse, the JSON array shape, unreadable dependencies of each kind, and no file writes including lease files. The command also MUST NOT modify any file. Scenario number 212 is the next free number at revise time.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T16:39:18Z
verdict: NO BLOCKERS
proposal_stem: sandbox-image-enumeration
content_digest: 7964699bcdc5a9d753e19fe780d489f52cc6910591773f40e016933588de5e16
