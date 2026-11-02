---
proposal: launch-preflight-while-queued.md
decision: modify
revised_at: 2026-11-02T16:48:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one modification, requested by the radar-and-deterministic-admission plan (w7ley3, slice 5 / plan assertion 19): a reused preflight pass MUST NOT stand in for, or let the launcher skip, any hold-file check. The clause, a Scenario 297 case and a check-fleet-launch harness case are added. The rule that the hold re-check is the last act before drive is deliberately NOT ratified here, because that is slice 5's own clause. The remainder is as proposed: the preflight runs while queued, a fresh pass is reused at the FIFO head, a stale one is re-taken there, FIFO bind order is kept with no second ordering rule, the mutex covers only count-to-release, and a failed preflight drops the ticket. This is conformance with the caller-side-gate framing of the section; it moves no Dispatcher-owned admission condition. Routed by legacy-coordinator-agent R301; implementing item bd-ib-x7bwug.

## Modifications

Added to the new paragraph: 'A preflight pass is not a hold check: a reused pass MUST NOT stand in for, or let the launcher skip, any hold-file check the launcher makes before `drive --action impl:<item>` starts.' Added a harness case: holding a launch at the head of the FIFO while the hold file exists even though the launcher's preflight pass is reusable. Added Scenario 297 case 'a reused pass does not skip the hold check'. Added the tests/heading-coverage.json TODO row (integration tier, owner bd-ib-x7bwug) and the matching tests/heading-coverage-debt.json row.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T16:47:40Z
verdict: NO BLOCKERS
proposal_stem: launch-preflight-while-queued
content_digest: 96455a89c1dcfab8a7dacdeb52bff9f3be213056e2996d98e60ff1d650f8fa85
