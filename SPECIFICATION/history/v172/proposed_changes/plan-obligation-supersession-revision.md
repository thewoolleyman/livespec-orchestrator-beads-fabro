---
proposal: plan-obligation-supersession.md
decision: modify
revised_at: 2026-10-20T14:38:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1:spec-implementation-lockstep
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep, routed by fleet coordinator gitops-fleet-capacity-monitoring as R301 for the maintainer. The clause 'Required result, budget and progress epoch' already requires an evidenced causal supersession before an unmet obligation is renamed but never defined one, so no sanctioned writer could record it; measured 2026-10-20 on plan epic bd-ib-ax3rds, whose mis-derived obligation impl:bd-ib-j6uvkj no writer could replace (prevention defect bd-ib-wnrird). The definition keeps every existing guarantee: a closed cause set with evidence verified at write time, no reset or postponement of the original deadline or handoff count, and expiry rules unchanged; it mirrors the explicit supersession that 'Relay delivery' already requires. The implementing work-item is bd-ib-egzipe. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes.

## Modifications

Two repairs from the first ratification-review round, which found that cause misderived verified provenance rather than error: M1, misderived additionally requires that the derived obligation name an impl step whose target work-item already carried a factory-safety label when the derivation was recorded, evidenced by the target's recorded label history at or before that transition, so a label applied afterwards never qualifies and a correctly derived obligation is never misderived (the time-of-derivation condition was added in round two); M2, every supersession's replacement result must be unsatisfied when written, so no cause can trade an unmet obligation for satisfied-result advancement. Scenario 211 gains the three matching refusal cases.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T14:37:33Z
verdict: NO BLOCKERS
proposal_stem: plan-obligation-supersession
content_digest: 1ed290b32ab147a2eddbe0e53885da0ad0bd49d87088821ad27b7b2a408613d0
