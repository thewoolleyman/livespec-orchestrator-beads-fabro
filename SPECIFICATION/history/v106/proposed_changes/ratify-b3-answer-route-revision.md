---
proposal: ratify-b3-answer-route.md
decision: accept
revised_at: 2026-09-07T13:25:27Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus (control-plane-accounts-and-dispatch-policy)
---

## Decision and Rationale

Ratifies the four already-shipped b3 answer-route mechanisms (marker, poison preflight refusal, valve run-account, comment-before-transition) so downstream consumers (console v049 Scenario 32) rely on ratified text, not implementation-only facts. No implementation change; the text describes shipped behavior verbatim. Maintainer go-ahead via retire-overseer standing directive 4.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-07T13:23:00Z
verdict: NO BLOCKERS
proposal_stem: ratify-b3-answer-route
content_digest: ed74bf44e2db120a1461264cee72a828402599d4312dde3b4622430c43f7b367
