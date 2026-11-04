---
proposal: proof-fidelity-recapture.md
decision: accept
revised_at: 2026-10-23T16:03:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which owns work-item bd-ib-v3uksp. Coordinator ruling R659 approved this remedy. Run 01M5JME62ZF8 of bd-ib-7k7re5 (2026-10-22) had a green implementation and a review approval, yet proof_verify recorded not_reproduced only because stdout and stderr interleaved differently on replay; the ratified text sent every not_reproduced to fix, which was handed a superseded capture's finding, correctly refused an artificial change, and ended needs_human on correct work. This revision makes proof_verify classify each not-reproduced difference as fidelity or behaviour (behaviour unless fidelity is positively shown); an all-fidelity verdict routes to proof_capture as a recapture under the shared two-lap recapture bound, never to fix; the behaviour bound and review-fix budget count behaviour verdicts only; and fix takes as its work order the record the entering stage graded in that visit, never a superseded capture. Five new Scenario 137 cases, one qualified Scenario 137 case and one Scenario 138 case; no heading changes. Independent gpt-6-astra review of the proposal: round 1 BLOCKERS 1, round 2 BLOCKERS 1, each answered by a numbered amendment; round 3 NO BLOCKERS. After rebasing onto v204, ratification review round 1 on the exact resulting bytes returned BLOCKERS 2 (the fix work-order trigger still covered fidelity verdicts; the recapture fallback named only the review record), answered by amendment 7; round 2 returned BLOCKERS 1 (Scenario 132 and the resume-stage derivation still routed every not_reproduced to fix), answered by amendment 8; the final ratification review is recorded below.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-23T16:03:30Z
verdict: NO BLOCKERS
proposal_stem: proof-fidelity-recapture
content_digest: c2d35b9d0f13a556f8c1b70f77cb68a82f9bf05535f43445d32a3d09e19212ec
