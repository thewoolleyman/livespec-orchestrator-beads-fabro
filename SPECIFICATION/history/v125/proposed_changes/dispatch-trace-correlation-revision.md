---
proposal: dispatch-trace-correlation.md
decision: modify
revised_at: 2026-10-11T04:59:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

No ratified heading governs the Dispatcher's correlation labels on fabro run, the TRACEPARENT handoff or the dispatch span, so the factory Definition-of-Done gate refused bd-ib-5jvgfr. This H3 places that surface under the section that already owns the receiver allowlist and the shared attribute vocabulary, and matches the current allowlist and the fork's accepted label and traceparent shapes.

## Modifications

From the independent reviews: (1) the identifier-shape test applies after surrounding whitespace is removed, matching the fork's trim-then-check; (2) TRACEPARENT names its shape (32 and 16 lowercase hex digits, neither all zeros); (3) the trace-id distinctness guarantee is replaced by a determinism requirement on a domain-separated, truncated SHA-256 derivation with a non-zero fallback, with collisions permitted; (4) dispatch-span export follows the section's bounded asynchronous telemetry and scrubbing rules and an export failure does not fail the dispatch.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-11T04:59:10Z
verdict: NO BLOCKERS
proposal_stem: dispatch-trace-correlation
content_digest: d9080cd308e189254ac1421143d3a722bd6d33173a23e73dbd63688f8b10cf4e
