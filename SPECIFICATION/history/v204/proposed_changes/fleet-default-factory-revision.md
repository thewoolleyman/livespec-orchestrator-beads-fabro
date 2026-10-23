---
proposal: fleet-default-factory.md
decision: accept
revised_at: 2026-10-23T14:34:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which owns work-item bd-ib-ep4eeo. The maintainer asked on 2026-10-22 (coordinator ruling R679) why fleet factory routing is duplicated in every repository; the R668 cutover took one config PR per repository plus a spec revision in every repository whose spec pinned the default name. This revision lets the host factory registry designate a fleet default (dispatcher.default_factory: fleet) and carry each factory's client settings, with committed values winning key by key. The fleet default is an implicitly declared factory, and a factory any dispatch reached through fleet keeps durable recorded-target standing for observation, recovery, availability and resume, so moving the default never orphans a run or hides a hold. Per v203, a fleet-derived pin binds a resume only; a fresh dispatch takes the current resolved default or overflow. Explicit selection and overflow entries still require a committed declaration. New Scenario 241; Scenario 212's undeclared case narrowed; heading-coverage row owned by bd-ib-ep4eeo. Independent gpt-6-astra review of the proposal: rounds 1-2 BLOCKERS, round 3 NO BLOCKERS; after rebasing onto v203, rounds 4-9 BLOCKERS (2, 2, 1, 2, 1, 1), each answered by a numbered amendment; round 10 NO BLOCKERS. Ratification review on the exact resulting bytes is recorded below.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-23T14:34:06Z
verdict: NO BLOCKERS
proposal_stem: fleet-default-factory
content_digest: f7637c19b85d78308bbc07abe3f729e467614bf52127ad03fdf36479ee8b33aa
