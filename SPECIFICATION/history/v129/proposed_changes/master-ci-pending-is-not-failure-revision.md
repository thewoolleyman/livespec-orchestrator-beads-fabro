---
proposal: master-ci-pending-is-not-failure.md
decision: modify
revised_at: 2026-10-13T07:24:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

A still-running default-branch CI run has not failed, yet the master-CI preflight refused it as unprovable with ERROR wording, journal status failed and red-branch recovery text. Measured 2026-10-13: dispatches of bd-ib-g6g3dg and bd-ib-jqvqlf were refused this way while master CI was queued or in progress, with 12 master CI runs in about 4.5 hours. Maintainer ruling 2026-10-13 (recorded as a scope event on plan epic bd-ib-jnpvh4): still running is not failed; fix it. The preflight now waits up to 1800 seconds, following the latest run, passes on green, refuses on red, and at expiry returns a deferral form of refusal (exit 3, journal status deferred, reason master-ci-pending, not-failed wording, no red-branch recovery text); a committed master-ci waiver still takes precedence. Fleet sweep: livespec-dev-tooling check-master-ci-green and the livespec-overseer drain engine already treat pending as non-blocking or wait; no other repository has this preflight. Implementing item: bd-ib-ex35cb. No cited design record is contradicted. Independent read-only review by OpenAI Codex gpt-6-astra (the configured ratification_reviewer_model): first pass, Codex session 01a1341f-8703-7603-968e-2c1cd3f50de4, returned two blockers (closed pre-dispatch outcome set and exit-code mapping; missing design-record citation), both fixed; second pass, Codex session 01a13421-ba12-79b2-934f-4afcad436760, returned NO BLOCKERS; the post-step doctor then failed two section-sign citations of a paragraph label, which were rewritten as rule references, and a third pass on the final bytes, Codex session 01a13424-48e1-7373-8ef2-be5303cc34f0, returned NO BLOCKERS.

## Modifications

Relative to the filed proposal: (1) the pending outcome is defined as the one DEFERRAL form of the existing pre-dispatch Refusal outcome, amended in the step discipline, exiting 3 and journaled deferred / master-ci-pending, and the Dispatcher exit-code table names it under exit 3; (2) the rule carries a rationale and a repo-qualified design-record citation, and states that a committed master-ci step waiver still waives the step before any waiting; (3) the progress line is SHOULD, not MUST; (4) Scenario 171's newer-run step is bounded by the original wait and its So-that line no longer promises callers need no retry loop.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-13T07:23:36Z
verdict: NO BLOCKERS
proposal_stem: master-ci-pending-is-not-failure
content_digest: 2d8e31c4ce83ce4bbfa1890d93831c8a96d9eec7d027716a5d1e82a299c947df
