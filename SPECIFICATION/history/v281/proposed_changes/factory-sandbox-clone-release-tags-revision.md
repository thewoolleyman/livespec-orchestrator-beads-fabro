---
proposal: factory-sandbox-clone-release-tags.md
decision: accept
revised_at: 2026-11-03T05:00:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under R301 by fleet coordinator legacy-coordinator-agent (the delegated decision recorded on the 2026-11-02 cut, re-confirmed on 2026-11-03 with the spec-version order v280 then v281). The rule closes a real gap that stale sandbox clone tags caused (bd-ib-ia6zbf). This is a re-cut of the 2026-11-02 v278 revision onto current master: the added text is byte-identical, and Scenario 298 now sits before Scenario 300 because 298 and 299 are unused. Independent sonnet ratification review of these exact bytes against current master returned NO BLOCKERS. v279 (codex-floor-reset-proximity) and v280 (a-spec-change-tier-verdict) touch neither clone preparation nor tags. Observation 1 from the original review is satisfied by the rule itself: the forced git fetch --tags brings every remote tag. The remaining observations are non-normative.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T04:59:04Z
verdict: NO BLOCKERS
proposal_stem: factory-sandbox-clone-release-tags
content_digest: b6a8032b013e6d77f29be18ac7dc4a29d7be9f89df7f63bff41161c04ef80b23
