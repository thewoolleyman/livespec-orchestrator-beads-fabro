---
proposal: plan-continuation-and-typed-kinds.md
decision: modify
revised_at: 2026-10-10T03:51:29Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accepted with modifications from two rounds of independent gpt-6-astra ratification review (see modifications). The attended picker and the closed set of next_action kinds were measured as the strongest stall cause on plan definition-and-proof-of-done (research notes 006 and 007, 2026-10-10): a session whose children are all closed can only record kind human and stop, and the maintainer's standing directive to continue has to be re-applied by hand at every resume. Realized: a continuation ruling recorded verbatim by an attended session; an attended resume that takes a dispatchable pointer under a current ruling and still raises the picker for human and none; four kinds (proof with capture:<epic> or verify:<epic>, review, archive, await with run:, gate:, item: or epic: refs) that carry required_result and budget like impl; pointer reconciliation before continuation that advances a satisfied pointer and reattaches an outstanding one to its live run; the kind check folded into plan_next_action_typed and a new plan_continuation_ruling check; the restraint budget extended to the new shapes. Scenario 168 added; tests/heading-coverage.json and tests/heading-coverage-debt.json co-edited with one owned TODO row naming epic bd-ib-7sjdzv until the implementing child is filed. Store-write consent, admission and the required-result budget rules are untouched.

## Modifications

Relative to the filed proposal, after the independent gpt-6-astra ratification review (tmp/ratification-plan-continuation.json, 2026-10-10T02:19:48Z, five blockers, four advisories): (B1) an await pointer required_result MUST be one of the result kinds the Shared authoritative result reader permits (the item_status or item_comment of the item a run or gate drives, a pull_request_state, a verified_proof on an epic); run: and gate: refs are observation handles only, and a run or gate that produces no permitted result is not awaitable. (B2, B3) reconciliation is defined by two findings: SATISFIED (the required result already holds; the pointer is stale and the resume advances under the ordinary rules) and LIVE RUN (an impl or spec-op pointer whose target a live run drives is rewritten as await with run:<id> as a representation change of the SAME obligation, keeping required_result, epoch, original deadline and handoff count, never extending the budget from the run deadline, with the existing expiry rules applying); an unsatisfied in-budget await is NOT stale and is not rewritten. (B4) the continuation ruling carries directive: (the maintainer words verbatim) and recorded-attended: true, the latter written only by the scope-event primitive, which refuses to record a continuation ruling from an unattended session; a ruling lacking any line is not current; a revoked ruling carries a by: line; the latest ruling in timeline order governs. (B5) the proof-sequence scenario is qualified by the archive contract own states: capture when no captured record postdates the last carrier-map event, verify when the latest is captured with no later verified record, review when the proof leg is met and no valid completeness evidence exists, archive when all three legs are met, and a later not_reproduced record returns to capture. (Advisory) the unattended no-ask rule covers the four new kinds explicitly; the kind check is folded into the existing plan_next_action_typed check (error) and plan_continuation_ruling is an error-level check naming the missing lines; the await-epic scenario names its result kind verified_proof. (Round 2, R2-B1) SATISFIED is checked first and LIVE RUN applies only to an outstanding obligation, so at most one finding applies. (R2-B2) the stale-closed-item scenario states its required_result as item_status closed. (R2-B3) the proof-sequence scenario is derived from the archive contract: capture while the proof leg is unmet and the newest record is not captured, verify while the newest is captured, review once the proof leg is met without valid completeness evidence, archive once all three legs are met with no further capture, and a not_reproduced record newer than every verified one returns to capture. (Round 3, R3-B1) the live-run scenario requires the result to be authoritatively unsatisfied with tracking checks permitting continuation. (R3-B2) the proof-sequence scenario keys capture and verify on the verified-record half of the proof leg and routes a missing human attestation to kind human, so no capture or verify repeats while only human evidence is absent.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: manual-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-10T02:30:46Z
verdict: NO BLOCKERS
proposal_stem: plan-continuation-and-typed-kinds
content_digest: ff457effc43f2c1538d7e3de035e4cfdfc94ddf442a05de6d665e0c898af11cc
