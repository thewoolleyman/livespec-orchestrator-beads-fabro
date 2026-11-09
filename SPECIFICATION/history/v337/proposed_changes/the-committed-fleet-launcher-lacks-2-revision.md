---
proposal: the-committed-fleet-launcher-lacks-2.md
decision: accept
revised_at: 2026-11-09T22:19:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. This defines a yielding ticket: a launcher yielding the FIFO head marks its ticket held=<cause>, and every queue reader skips it whichever launcher marked it. It also adds the canary repository hold with its exemption list. These are bd-ib-4xqmqh Definition of Done assertions 10 and 11, added after the 2026-11-09 incident, and the ruling path is coordinator path (b). It composes with the-committed-fleet-launcher-lacks, whose gmktec allowlist exception was scoped in that decision's modifications so the two skip rules do not conflict.

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
reviewed_at: 2026-11-09T22:19:09Z
verdict: NO BLOCKERS
proposal_stem: the-committed-fleet-launcher-lacks-2
content_digest: 0bb331eb72490f510ab199791ec12eceb94b1f95c4138ca5c37ad772c3e915f9
