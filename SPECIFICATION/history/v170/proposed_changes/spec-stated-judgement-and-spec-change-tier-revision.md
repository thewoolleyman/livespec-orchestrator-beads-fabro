---
proposal: spec-stated-judgement-and-spec-change-tier.md
decision: modify
revised_at: 2026-10-20T11:52:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1:spec-implementation-lockstep
---

## Decision and Rationale

Accepted with modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep for plan epic bd-ib-ax3rds (Definition of Done assertions 1, 2, 3 and 6). Ruling (A), recorded on the epic on 2026-10-20 by the fleet coordinator gitops-fleet-capacity-monitoring for the maintainer, governs the release of a held item: releasing a spec-change-tier item on ratification with no human valve is the maintainer's own refinement of the 2026-07-10 spec-change boundary, per item (5) of the maintainer ruling recorded on bd-ib-7sjdzv on 2026-10-20. The invariant is kept: the spec change itself always goes through propose-change and revise, and the item is never dispatched or auto-admitted while it is held. The proposal's contracts.md text alone would have left spec.md and constraints.md stating the 2026-07-10 boundary absolutely, so this revise co-edits them to say the same thing. Release adds no human step and does not override the item's own admission_policy, which is independent of the spec hold; that is ruling (A), not alternative (B), which would have added a human approve to every released item. The judgement the Dispatcher consumes is the livespec_runtime.spec_stated family ratified in livespec-runtime v027 (PR 736). The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes.

## Modifications

Four co-edits beyond the proposal's two contracts.md edits and Scenario 206, all from ruling (A): M1, spec.md Terminology 'Spec-change slices' says the item is never factory-dispatched or auto-admitted while it is held for its proposal's ratification, and that once the revision record is accept or modify and the judgement returns stated it routes as ordinary dispatchable follow-up work, naming that release as the maintainer's 2026-10-20 refinement of the 2026-07-10 declaration; M2, spec.md Dispatcher policy settings says a spec-change-tier item is never auto-approved while it is held; M3, the constraints.md plan-child disposition paragraph routes a spec-change child to propose-change only while it is held; M4, the constraints.md autonomy-tier paragraph (formerly tracked by bd-ib-yykjko) says the tier is decided by the spec-stated judgement and recorded at classification, and the fail-closed rule reads that recorded classification instead of an unratified datum. Four repairs from the first ratification-review round: M5, a recorded spec-stated or Definition-of-Done verdict is reused only while no specification revision has been ratified since it was taken, so the judgement that releases a held item runs against the ratified specification, and the drain exclusion of a refused item lifts on a new revision; M6, release on ratification removes the spec hold only: the item stops being spec-change tier and routes as its effective admission_policy decides, auto to ready and manual to pending-approval for the approve valve, and Scenario 206 gains the manual case; M7, Scenario 206 requires a stated verdict beside the commitment hint for a follow-up to be exempt, and adds the case where a hint beside unstated behaviour does not exempt the item; M8, the Dispatcher exit-code list names the ratification hold among the exit 5 refusals. Two repairs from the second round: M9, Scenario 174 adds the no-intervening-ratification condition to its verdict-reuse case, and lets a ratified revision, as well as a criteria change, return a refused item to enumeration, following M5; M10, the constraints.md plan-child paragraph admits a hint-carrying follow-up only when the judgement reports its behaviour stated, and no longer says a spec-change slice cannot carry a hint, following M7. The implementation of M5 and M9 (verdict invalidation on ratification) is owned by bd-ib-m76p2n, and M6, M7 and M10 by bd-ib-57ss2n.

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md
- spec.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T11:51:26Z
verdict: NO BLOCKERS
proposal_stem: spec-stated-judgement-and-spec-change-tier
content_digest: 74ffc2fac59daa19796e9b6e7683edcf132d4d7fe4f2d3b1d74bc602d5c13734
