---
proposal: refresh-hook-refusal-routes-to-fix.md
decision: modify
revised_at: 2026-11-01T23:58:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:implement-test-performance
---

## Decision and Rationale

MODIFY. Accepts the proposal as filed: a commit that a refresh itself makes (the merge commit of a merge refresh, or a replayed rebase commit) and that the repository's commit hook refuses while no path is conflicted becomes a refresh-repair cause. The stage restores the pre-refresh head, records a brief naming the hook's failed targets and its last 80 lines of output, and routes to fix instead of ending at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT. One scenario is added under Scenario 176. The modification, taken from the independent reviewer's nit: the same cause is mirrored into the two stage-level cause lists, in the publish_draft paragraph and the pr_refresh paragraph, so that they no longer name only conflicts and gate rejections. Motivation: on 2026-11-01 two fully green factory runs ended this way, bd-ib-kkuohy and livespec-dev-tooling-hpydsh. No design record is contradicted, because the paragraph's existing rule distinguishing gate rejection from push or auth failure is unchanged, and a hook refusal of the refresh's own commit precedes any push. No ## heading changes. Decided under delegated revise_decision_mode by plan session implement-test-performance (livespec-dev-tooling epic sv6m5p; maintainer autonomy ruling 2026-11-01). Re-cut as v272 on top of v271 (lupvil, PR #4130) per spec-implementation-lockstep's ordering; a FRESH independent read-only sonnet review found NO BLOCKERS on these re-cut bytes, and found no interaction with v271. Nits left: one over-long wrapped line, and the needs_human sentence's unqualified scope, which is harmless.

## Modifications

Mirror the new cause into the publish_draft and pr_refresh stage-level cause lists (contracts.md ~lines 3387 and 3447).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T23:56:00Z
verdict: NO BLOCKERS
proposal_stem: refresh-hook-refusal-routes-to-fix
content_digest: 5f789f15d92bb4d1de04584391aa29ccb2c411aabb17969b4bd25d7244a69c7d
