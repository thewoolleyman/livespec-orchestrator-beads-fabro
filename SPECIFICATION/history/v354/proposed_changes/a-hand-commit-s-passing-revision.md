---
proposal: a-hand-commit-s-passing.md
decision: modify
revised_at: 2026-11-11T17:44:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratify the proposal's constraints.md paragraph verbatim. bd-ib-3k3xh7's filing tier is spec-change/partial against v353 '## Pre-push gate refinements' (linked topic a-hand-commit-s-passing), and legacy-coordinator-agent holds approve until this topic ratifies. This repository sets both delegated_gate and delegated_pre_commit, so livespec-dev-tooling contracts.md §'Delegated pre-push gate' Same-tree delegated pre-commit verdict already binds its pre-push gate. Today dev-tooling/just-check-pre-push.sh consults only green-token-scope.sh, which refuses every pre_commit_aggregate token, before gate_remote_delegate run. So a hand commit's passing delegated pre-commit Job is followed by a second full-suite gate Job at push: 2,262 s of check-pre-push on this proposal's own push (gate 20261111T164638Z-1030302). The paragraph states this repository's adoption: one library call before its own green-token check, the qualification, no gate Job and no fall-through, the members still run, the printed lines, the fallback, and the precedence of the deletion-only skip. It is spec-first, and bd-ib-3k3xh7 owns the change. Decided by the implement-test-performance plan seat under delegated decision mode, in the v354 slot legacy-coordinator-agent assigned (~17:48Z).

## Modifications

Layout only, no change of obligation. The proposal wrote its scenario heading inside a gherkin fence and ended it with a step combining a second case ('And when the worktree is dirty or its HEAD tree is not T, it MUST gate the push exactly as it does with no such evidence'). It is ratified in this repository's scenario format: the H2 heading sits outside the fence, then a gherkin Feature with two indented Scenarios. The first carries the qualifying-verdict steps verbatim. The second carries the dirty-or-different-tree fallback as its own Given/When/Then. Spec-first TODO coverage and debt rows are owned by bd-ib-3k3xh7.

## Resulting Changes

- constraints.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T17:43:53Z
verdict: NO BLOCKERS
proposal_stem: a-hand-commit-s-passing
content_digest: 8dab8affaf5b5a92bf98a06d5107e2b7717c80964e168ceea1405aa517894fc9
