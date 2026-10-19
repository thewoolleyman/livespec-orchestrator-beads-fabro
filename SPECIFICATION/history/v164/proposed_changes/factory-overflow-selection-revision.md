---
proposal: factory-overflow-selection.md
decision: modify
revised_at: 2026-10-19T03:08:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications by the plan petri-factory-on-gmktec session (66e3daf2-a26d-486d-87fd-500456edeffe) under spec_governance.revise_decision_mode delegated and the plan's standing rulings: petri-ruling-accept-half-installed-reunpack-and-stop-asking (2026-10-17T21:55Z, a spec proposal fixing a measured defect blocking plan work is session-ratifiable after independent review) and the maintainer's 2026-10-19 direction relayed verbatim by coordinator gitops-fleet-capacity-monitoring: "Yes add GMK to the factory map. There's no reason that that shouldn't have been done already. The whole plan was to get it usable and start using it." The proposal was restated before ratification after a measurement: hp's server reports server.scheduler.max_concurrent_runs 10 and petri's reports 2 (fabro settings --server, 2026-10-19 03:01Z), so a first-free-slot rule would almost never select petri; the rule chooses the least-utilized candidate with a free slot. The scenario is numbered 203 because v163 took 201 and branch spec/agent-stage-boundaries holds 200-202. Review history: independent read-only gpt-6-astra round 1 (codex session 01a1521e-d0ed-7463-8d34-c52ad703fdfd) returned two blockers: the resume section's factory-order parenthetical stayed unamended, and a capacity fallback to an unresolvable registry-backed default conflicted with the registry refusal. Both are fixed in the resulting files, and Scenario 203 gained an equal-utilization tie case, a failed-read journal assertion and an explicit --factory case. Round 2 (codex session 01a15220-a575-7220-9cf4-591f44a1783a) returned NO BLOCKERS on these exact bytes and recomputed the digest. Scenario 203 gains a heading-coverage TODO row and a debt-register row owned by implementation child bd-ib-pzdwej. Step 3.5: the stale-branch precondition is skipped explicitly; its findings are this proposal's own branch, which carries this revise, and other threads' spec branches this pass does not touch.

## Modifications

Resulting files depart from the proposal text in four ways: (1) the resume section 'Resume from a published pull request (resume --item)' now resolves its factory through the amended selection order instead of its own parenthetical; (2) selection never refuses on CAPACITY grounds, while a default reached by fallback is resolved and admitted exactly as an explicit selection, so an unresolvable registry-backed default is refused under the registry section; (3) the recorded-factory sentence routes a no-longer-declared recorded name through overflow selection when configured; (4) Scenario 203 adds an equal-utilization tie case, a failed-read journal assertion and an explicit --factory pinned case.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-19T03:08:16Z
verdict: NO BLOCKERS
proposal_stem: factory-overflow-selection
content_digest: 27dbcd8f70b42dedc26b625e373346af2ed01284d860ab9cabc8b2e956d55823
