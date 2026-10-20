---
proposal: stale-fabro-assignee-reconciliation.md
decision: modify
revised_at: 2026-10-20T10:43:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Accepted with modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (epic bd-ib-ax3rds), at fleet coordinator gitops-fleet-capacity-monitoring's routing R293. The proposal closes a measured gap: reconcile-runs named no remedy for a ready item still assigned fabro whose last run is terminal (bd-ib-z2y4ca, bd-ib-t4dtx4, bd-ib-ukht2p failed; bd-ib-ma3fvj succeeded with an open PR), because the ratified section surveys only active claims, so the stale assignee survived and an ownership sweep nearly dispatched ma3fvj fresh on top of its open PR. The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on the exact resulting bytes after six rounds. The Scenario 210 coverage entry and debt-register row land in the same change, owned by bd-ib-3lbt4o.


## Modifications

The resulting bytes carry the proposal's intent with these modifications from six gpt-6-astra ratification rounds:
- M1 (round 1 B1, B4; round 3 B1, B2): instead of an admission bar keyed on hold reasons, every stale assignee whose run stamp names a run is released for recovery, so its next dispatch is graded by the existing recovery routing (resume a published pull request when its preconditions pass; hold for a live earlier run, a live owner, a merged pull request or an unobservable measurement; otherwise seeded or fresh). The released-for-recovery definition in Factory-configurable ACP fallback priority is extended to the stale-assignee-clear record and to a stale assignee itself, and the resume introduction's exception list names this route.
- M2: clearance is assignee housekeeping only: attributed to this host by a non-pending stamp, run terminal (failed or succeeded) or positively absent, no live owner; it journals stale-assignee-clear with run state failed, succeeded or absent and writes one comment, status, labels and stamp unchanged.
- M3 (round 1 B2, B3): claim-changed is redefined for this subject (no longer ready, no longer fabro, pending stamp, or a different run), and a human move before the assignee write is respected and held.
- M4 (round 1 N2): clearance effects are keyed by item, run and the stale-assignee-clear kind, and the Residual race window covers the assignee write.
- M5 (round 2 B1; round 3 B2; round 3 N1): reconcile-merged also accepts a ready item that recovery routing holds for a merged pull request of its latest dispatch, applying every guard and the post-merge disposition with ready in place of active: a green janitor writes ready to acceptance and every failed guarded precondition leaves the item ready.
- M6 (round 2 B2; round 4 B1): a stale assignee with a pending or unreadable stamp is held (attribution-pending or claim-unattributable), is not released for recovery, and its admission is unchanged by the clause.
- M7 (round 3 N2; round 5 N1): the resume promise is qualified, and the resume introduction defers to recovery routing (seeded, fresh or held) instead of always seeding.
- S1 (rounds 1, 4, 5): Scenario 210's Background carries only the ready, fabro and no-marker facts; scenarios cover failed, absent and succeeded-open-PR clearance, the hold outline, a human move, a held item still routed, merged-PR recovery from ready before and after clearance, a pending stamp, an interrupted clearance replay, and an idempotent second pass.


## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: manual-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T10:43:09Z
verdict: NO BLOCKERS
proposal_stem: stale-fabro-assignee-reconciliation
content_digest: 8742708bd916024b9f9f3268e4beb2f8d87b1f721e66933d78bbc70d1d6f068c
