---
proposal: delegated-valve-authority.md
decision: accept
revised_at: 2026-11-03T07:25:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as proposed. The maintainer ruled on 2026-11-02 (plan-scope-event on livespec-dev-tooling-6tgd2z at 23:22:22Z) that the coordinator's R493 delegation of the human valves becomes a first-class concept so delegated presses stop blocking. The clause makes the delegated press verifiable against a committed grant, keeps R493's credential, irreversible and outward-facing exclusions mechanical through a code-fixed allowlist, records every delegated press as delegated without a human: identity, and binds the behavior with Scenario 301. The independent reviewer's non-blocking notes (a release-spec-tier cross-reference, extra refusal shapes in the scenario) are covered by the implementation's tests and can be tightened in a later pass.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T07:24:55Z
verdict: NO BLOCKERS
proposal_stem: delegated-valve-authority
content_digest: 52dc3fb2b20a6af55ee15e6648929eaa6df7a663f589ea2e92b0f26d8c7682e5
