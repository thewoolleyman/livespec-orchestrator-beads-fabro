---
proposal: workflow-declared-node-timeouts.md
decision: modify
revised_at: 2026-11-07T20:21:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent under R301 delegated authority on 2026-11-07: ACCEPT MODIFY on content digest adc8d892, after reading the diff of both files against 542a6d482. A workflow's declared node timeout now stands unless configuration names the node, which closes the contradiction inside section ACP node timeouts in favour of its Resolution layers paragraph. An undeclared node keeps 1800 seconds, so the maintainer's 2026-08-26 ruling (bd-ib-cnkf) stands. This is the coordinator's decision, not the maintainer's. Measured motivation: run 01M6V85A0CM5QXY0RJFRSK8XAP rendered timeout 1800s on the commit settle nodes while the shipped graph declares 3900s. Implementation is bd-ib-2eyiwy.

## Modifications

Compared with the proposal: (a) Scenario 89's default-target and configured-node cases are reworded, because their every-node-1800 text contradicts this change and the proposal missed it. (b) The settle clause names implement_commit_settle, fix_commit_settle and review_fix_commit_settle, and a resolved settle timeout of 300 seconds or less is rejected before any run exists. (c) The new scenario is numbered 325, since 323 and 324 are taken; its undeclared-node case names the dispatch record's layer; three cases are appended: a settle timeout leaving no wait is refused, the shipped graph keeps the deliberate reduction, and a low declaration names its measurement. (d) The scenario's Governing clause line also names the two clauses those appended cases exercise.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T20:18:30Z
verdict: NO BLOCKERS
proposal_stem: workflow-declared-node-timeouts
content_digest: adc8d892eca64b6bdda2966bc19eab494c96639c552b2d04cb866533cdca4ece
