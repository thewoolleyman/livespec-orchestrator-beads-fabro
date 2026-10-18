---
proposal: stranded-claim-release.md
decision: modify
revised_at: 2026-10-18T05:36:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:run-lifecycle-false-verdicts
---

## Decision and Rationale

Ratifies, as Scenario 196, the claim half of run reconciliation, which bd-ib-m0t0 implements. The spec already names reconcile-runs as the remedy for a stranded claim, but §"A factory run never awaits a human" reconciles only runs that still exist, so a claim whose run vanished stays active/fabro until a hand move valve. bd-ib-m0t0's Definition of Done had no governing scenario, which is the shape the dod_gate refused three times on 2026-10-18. The gitops-fleet-capacity coordinator directed this ratification as grooming (R143 follow-up) and ruled the residual-race policy question R144 (parity with the Dispatcher's own terminal path, with an explicit residual-race clause citing bd-ib-jjws2). Ratified under delegated revise with an auto-spawned gpt-6-astra review.

## Modifications

Five gpt-6-astra review rounds. Round 1 (BLOCKERS): the hold vocabulary could not represent unobservable attribution, liveness or terminal evidence; a generic terminal release conflicted with the adapter-launch route; Scenario 193 had overbroad release cases. Round 2: terminal runs now receive the Dispatcher's own terminal disposition (first-stall, provider-limit or adapter-launch release with replay, the repeated adapter-launch route, or the needs-human rest), and the only new release is the absent-run release, bounded to one per consecutive sequence (a repeat rests as run-absent-repeated). Round 2 (BLOCKERS) found cross-host ownership unsafe and predecessor history unrepresentable. Round 3: the ledger run stamp names the dispatching host and only that host recovers (owner-elsewhere), and a history-unavailable hold was added. Round 3 (BLOCKERS) raised server-side exclusion, escalated as policy; the coordinator ruled R144 for parity. Round 4: an explicit Residual race bullet citing bd-ib-jjws2; the recovery lock is pinned to the primary checkout; writes are ordered journal, comment, transition, with the stamp re-read immediately before the transition (claim-changed) and convergent replay (effect-unobservable). Round 4 (BLOCKERS) found the disclosure inaccurate. Round 5: admission writes a pending stamp (attribution-pending), the false no-newer-claim sentence is removed, the lock is scoped to recoveries, and the residual disclosure covers any conflicting write on any host. Round 5 returned NO BLOCKERS with one non-blocking advisory (say explicitly that a pending stamp carries the selected declared factory), left as reviewed and carried to bd-ib-m0t0's implementation brief. Two concurrent revisions landed first (v155, bd-ib-cap6t7, Scenario 194; v156, bd-ib-kcq6pu, Scenario 195), so the resulting files were rebuilt on that master with the new scenario numbered 196, and a sixth gpt-6-astra round re-reviewed the rebased bytes and returned NO BLOCKERS with the same advisory. The Scenario 196 tests/heading-coverage.json and heading-coverage-debt.json entries land as a same-PR hand edit outside the spec target, as v154 did; work item bd-ib-m0t0 owns the binding.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T05:35:29Z
verdict: NO BLOCKERS
proposal_stem: stranded-claim-release
content_digest: c6bbaed1f41f78c47e769543ffa01010d8ac26ae9792ccee8183fd48ae187999
