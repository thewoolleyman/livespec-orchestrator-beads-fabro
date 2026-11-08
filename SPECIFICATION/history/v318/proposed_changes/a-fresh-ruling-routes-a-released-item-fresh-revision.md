---
proposal: a-fresh-ruling-routes-a-released-item-fresh.md
decision: modify
revised_at: 2026-11-08T01:45:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session a21903eb) under R301 delegated authority and the maintainer's 2026-08-26 'I authorize all revises', on 2026-11-08: ACCEPT MODIFY on content digest 421c6148..., the third review round. This is the coordinator's decision, not the maintainer's; the plan seat publish-draft-green-work-loss (session 030f6206) drafted the bytes. Basis, as the coordinator stated it: modifications (1) to (3) make the released-candidate grading and the seed paragraph agree with the new fresh-ruling route, and the PR #4615 clarification is consistent with the preservation rules, because a fresh ruling never deletes or moves a needs-human or preservation ref, the stale publish branch is preserved before its reclaim, a non-fallback refusal and an untaken needs-human listing still hold the item, and a ruling is consumed once with reconciliation backfilling the consumed comment. The proposal closes a measured gap: a recovery-released item whose preserved trees are stale or wrong (bd-ib-72hvx5, about 950 commits behind master; bd-ib-ltlg4i) had no route but seeding from one of them. Independent sonnet review reported NO BLOCKERS with notes on round 1, all applied; four blockers on round 2, each a behaviour with no scenario, all fixed by added cases; and NO BLOCKERS on these bytes in round 3. Fleet scope: the route lives in the orchestrator's shared recovery routing, which every repository dispatched through this plugin's Dispatcher uses through its pinned build, so no per-repository sweep is owed.

## Modifications

Compared with the proposal: (1) the released-candidate grading sentence 'fresh only when preserved work is confirmed absent' also gains 'or a current fresh ruling governs the item', to agree with the edited route list. (2) The clarification recorded on bd-ib-xz35zu from PR #4615 (bd-ib-oknwxm): a current fresh ruling routes fresh even when preserved work is not confirmed absent, including for an item whose earlier-run identifiers name no run; only a non-fallback refusal or a needs-human listing that cannot be taken holds the item, no other preserved-work measurement holds it, and the ruling stays current under either hold. (3) In the seed-ruling paragraph, 'Routing MUST take its seed from the ruling' reads 'from a current seed ruling'. (4) The scenario is numbered 327, the next free number, and carries twelve cases rather than the proposal's four: added are no run identifiers, precedence over resume, the untaken-listing hold, the reclaim preserving the head first, the command writing and journalling, the command refusing on the template-opener detector, a later seed ruling replacing a fresh ruling, and reconciliation adding a missing consumed comment; the first case also asserts the needs-human ref still exists. The paragraph names Scenario 327. Its heading-coverage and heading-coverage-debt entries are edited directly in the revise commit, owned by bd-ib-xz35zu, because resulting_files cannot reach tests/.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T01:44:52Z
verdict: NO BLOCKERS
proposal_stem: a-fresh-ruling-routes-a-released-item-fresh
content_digest: 421c614856f2c0ae6cb1010244656209aba788134f5c9f04bed2557a3b3a64ba
