---
proposal: misderived-proof-step-with-open-carrier.md
decision: modify
revised_at: 2026-10-22T05:54:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:petri-factory-on-gmktec
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session petri-factory-on-gmktec (0b9831de, plan bd-ib-fyozyd), under coordinator rulings R562 (file this carve-out) and R202 (spec drafting never blocks on a human). The widened misderived case keeps the cause set closed and adds no new cause: it qualifies only a plan-level step a derivation wrote while a carrier named by the epic's latest carrier-map scope event was not closed, with ledger-verifiable evidence, and every budget, idempotency and expiry rule of the paragraph is unchanged. No design record is cited by the paragraph, and the change contradicts no ratified clause. The configured ratification reviewer, gpt-6-astra, in separate read-only sessions, returned NO BLOCKERS on the exact resulting bytes in round 2 (digest d22ec2a1e72e849f626198a4026d8033551a2a5faaf7c60a247ae27c4d79a062), after round 1 found one blocker that is repaired in these bytes.

## Modifications

Beyond the filed text: the accepted Scenario 211 case also requires that the carrier is still not closed when the supersession is written, and names the replacement as an await whose required result is that carrier's item_status closed, so the replacement is unsatisfied at write time as the paragraph requires (gpt-6-astra round 1 finding).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T05:53:52Z
verdict: NO BLOCKERS
proposal_stem: misderived-proof-step-with-open-carrier
content_digest: d22ec2a1e72e849f626198a4026d8033551a2a5faaf7c60a247ae27c4d79a062
