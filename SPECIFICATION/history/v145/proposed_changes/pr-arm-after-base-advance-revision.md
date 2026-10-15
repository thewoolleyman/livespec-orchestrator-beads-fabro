---
proposal: pr-arm-after-base-advance.md
decision: modify
revised_at: 2026-10-15T16:48:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications. The proposal closes a ratified-text gap. Default-branch movement that lands between pr_refresh and the pr arming ended proof-verified runs at needs_human: run 01M4ZVSKDP1V on PR 3014. An armed pull request overtaken by a later conflicting commit ended in an unnamed merge-poll timeout: PR 3035. Approval: coordinator session gitops-fleet-capacity-monitoring approved the proposal under the maintainer's authorization recorded on livespec-dev-tooling-dfixhe (00:08Z and 00:22Z rulings, and ruling (5) at 00:09Z: spec revises are approved by the driver after a Fable subagent review). Its Fable review returned BLOCK on 52f14354 (three blockers) and APPROVE on the rework 5ca705cd; the delta-review tidies were folded into 01f851db, which merged as PR 3062 (7ba95376). The independent gpt-6-astra ratification review returned BLOCKERS in round 1 (arming exclusivity contradicted the host-side merge-hold release) and NO BLOCKERS in rounds 2 and 3 on the exact final bytes (round 3 re-reviewed the unchanged bytes under the spec-target-relative digest).

## Modifications

1. The pr routing sentence names pr_route as the node the run returns to pr_refresh through, and the unexpected-head case reads 'as for any unexpected head'. 2. The arming-authority sentence is scoped to 'Within a run'. The host-side hold release of 'The per-item merge hold' is named as the one arming outside a run; it MUST NOT arm while a run of the item is live, and it MUST arm only a pull request whose current head the latest verified or carried_forward record of the item's latest run names, refusing otherwise (ratification round-1 blocker). 3. The new ending paragraph closes with the sentence naming Scenario 184 as its exercising scenario. 4. Scenario 184 gains a sixth case: a merge-hold release cannot arm a head that no proof record names. 5. The Scenario 184 heading-coverage row is TODO, owned by implementation child bd-ib-3hpdvm, with a matching debt-register row first seen 2026-10-15.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T16:47:54Z
verdict: NO BLOCKERS
proposal_stem: pr-arm-after-base-advance
content_digest: 2562c48bfa8b63864b3e75f465ac9fc45eaa9edd05f138128e905c806e0bfb8c
