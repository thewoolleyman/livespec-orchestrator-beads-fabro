---
proposal: exhaustion-record-per-credential-identity.md
decision: accept
revised_at: 2026-10-16T19:59:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-bd-ib-jxvgq5
---

## Decision and Rationale

Accepted under maintainer ruling R76 (recorded on livespec-dev-tooling-dfixhe 2026-10-16 19:2xZ: the exhaustion-record fix is priority and the maintainer pre-approves ratification) and the delegated revise authority recorded there. Measured defect: the observed provider-exhaustion record is keyed only on the vendor, so after a credential rotation records minted by runs still finishing on the exhausted account refused dispatches on the fresh account (2026-10-16, refusals until 17:50:19Z). The accepted clause scopes the record to the opaque credential identity the admission session-headroom assessment already journals, keeps records distinct per identity, keeps vendor-wide coverage for identity-less records and fails closed on an absent identity; Scenario 186 states it. Independent reviews: Fable draft review BLOCK then PASS; gpt-6-astra ratification review NO BLOCKERS; Fable quality review of the resulting diff CLEAN. Re-run on master 6f4c80d8 as the next revision after a concurrent single-topic revise took v149; Scenario 186 keeps its reserved number. Carrier work-item bd-ib-b53dhr owns the Scenario 186 heading-coverage entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T19:59:00Z
verdict: NO BLOCKERS
proposal_stem: exhaustion-record-per-credential-identity
content_digest: cd330f11c4dec6643f05521e09b92d64dcfae349cdd60f036a19c1e89058f158
