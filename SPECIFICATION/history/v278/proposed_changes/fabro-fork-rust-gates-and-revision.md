---
proposal: fabro-fork-rust-gates-and.md
decision: accept
revised_at: 2026-11-02T19:14:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-test-gate-load
---

## Decision and Rationale

No ratified text names a venue for the fork's carrier-branch gates or the pinned carrier build, so bd-ib-dqxcsh was held at the spec-change tier under §'Fabro runtime constraints'. The rule constrains how the factory's pinned engine is gated and built, beside the existing Carrier branch and Rebuild-and-re-pin bullets, so it is a constraints.md bullet in that section, with Scenario 300 carrying it. It contradicts no existing clause: the runbook-lockstep rule already places operational commands in the runbook and hand-build guidance, which this bullet points to.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T19:11:20Z
verdict: NO BLOCKERS
proposal_stem: fabro-fork-rust-gates-and
content_digest: 2232903ccdf875e7499ad2451e089a9e23b42ab61c5a04e582cc193c0f1592e0
