---
proposal: dispatcher-owned-admission-gates.md
decision: modify
revised_at: 2026-10-18T15:28:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:run-lifecycle-false-verdicts
---

## Decision and Rationale

Ratifies, in the existing section 'Dispatch preflight and post-merge step discipline', that a caller of drive or of the Dispatcher does not gate a dispatch on the default branch's CI, names the three admission conditions the Dispatcher owns (the bounded master-CI preflight, the admission session-headroom assessment, and plugin build currency surfaced and refused only below a committed minimum_release floor), and names what a caller may add (factory host capacity, its own launch slot, launch spacing). Maintainer-directed via work-item bd-ib-zygea5 after nine launch loops held launches on a pending master run on 2026-10-18.

## Modifications

Two gpt-6-astra review rounds. Round 1 returned NO BLOCKERS with three advisories, all adopted: item 1 states the distinct PENDING/deferred outcome on window expiry; item 2 defers to the full headroom clause including its exceptions and parked-rework preservation; the MAY paragraph states a caller-scheduled launch slot is not a second repository-capacity authority. Round 2 returned NO BLOCKERS on the final bytes.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T15:28:46Z
verdict: NO BLOCKERS
proposal_stem: dispatcher-owned-admission-gates
content_digest: 06a87654d671c60bd93c27c3d47cf0315e1701f015e5cadc7a3cd5ea5525e86e
