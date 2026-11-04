---
proposal: fresh-dispatch-ignores-recorded-factory.md
decision: accept
revised_at: 2026-10-23T13:16:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which owns work-item bd-ib-2b2uqa. The fleet coordinator (gitops-fleet-capacity-monitoring, 2026-10-23 08:4xZ, relaying the maintainer's cutover direction under R668 and R301) ruled that a recorded factory binds only a rework of the same run lineage, never a fresh dispatch, routed the change through propose-change and revise, and rejected removing legacy from the factory tables before the bd-ib-iud52v soak ends. The ratified order put the item's recorded factory ahead of dispatcher.default_factory for every dispatch, so after the petri cutover every item that ever ran on hp still routed back to hp on its next fresh dispatch (measured on tdd-proof-lv352h, 2026-10-23T08:12:33Z; 15 non-closed items in 7 tenants record legacy). The revision restricts the recorded-factory step to a dispatch whose route is resume (an explicit resume --item, or recovery routing's resume route inside dispatch or loop), the one route that continues the run lineage, and makes every other dispatch a fresh one that reads no recorded pin. Recorded-target readers (reconcile, liveness, claim stamp run target, adapter launch evidence, acceptance, a resume's earlier-run read) are unchanged. Scenario 182's default-switch case and Scenario 203's pinned case are amended and six Scenario 203 cases added; no heading changes. Independent gpt-6-astra review of the proposal: round 1 BLOCKERS 2 (Scenario 182 contradiction; classification by command rather than recovery route), both fixed; round 2 NO BLOCKERS. Ratification review on the exact resulting bytes is recorded below.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-23T13:16:21Z
verdict: NO BLOCKERS
proposal_stem: fresh-dispatch-ignores-recorded-factory
content_digest: 6e88e9415953d7073649dfd883b87f57da281708dbae84ad5b6767ea475eee12
