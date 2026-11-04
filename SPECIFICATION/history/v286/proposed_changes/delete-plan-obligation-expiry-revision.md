---
proposal: delete-plan-obligation-expiry.md
decision: accept
revised_at: 2026-11-03T14:25:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Implements the maintainer's attended ruling recorded verbatim on livespec-dev-tooling-6tgd2z (2026-11-03T13:48:23Z) to delete the plan stall rule, as scoped by the fleet coordinator (legacy-coordinator-agent, R301). A plan budget becomes report-only: an overdue obligation never refuses a write, never needs a recovery attempt, ruling or human decision to continue, and never makes resume_directive withhold its executable action. The rename refusal and the evidenced-causal-supersession requirement are deleted with it, because they existed only to stop a rename evading expiry; a stale result is now re-aimed by an ordinary write recorded as a replacement event. Deletion, not a toggle.

## Resulting Changes

- contracts.md
- scenarios.md
- spec.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T14:25:37Z
verdict: NO BLOCKERS
proposal_stem: delete-plan-obligation-expiry
content_digest: a1081cf04f2093c7ad2cf59149265d165e91804cf16ec8079a400f3b1d6134f7
