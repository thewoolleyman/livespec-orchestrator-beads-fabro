---
proposal: proof-record-per-assertion-verdict.md
decision: modify
revised_at: 2026-10-18T05:03:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:definition-and-proof-of-done
---

## Decision and Rationale

Accepted. Work item bd-ib-rszkjc merged as pull request 3130 with a correctly attributed verified record whose only Reproduced: line was record-wide, so the acceptance pass read every assertion as unevidenced and parked correct merged work where no re-run can move it. The record clause now requires each factory_captured assertion section of a verified or not_reproduced record to carry its own prose Reproduced: line and forbids reading another section's verdict for it, which ratifies what the reader already enforces fail-closed. A command node proof_grade between the verified outcome of proof_verify and pr_refresh grades the record with the acceptance pass's own reader before the merge, re-entering proof_verify inside its existing visit cap so the correction is a new record. Scenario 195 added (193 is reserved by the in-flight proposal stranded-claim-release, and 194 was taken by v155); tests/heading-coverage.json and tests/heading-coverage-debt.json co-edited with one owned TODO row naming bd-ib-kcq6pu. Maintainer ratified in session 2026-10-18.

## Modifications

Relative to the filed proposal, after two rounds of independent gpt-6-astra ratification review (round 1 at 2026-10-18T04:34:04Z, one blocker; round 2 at 04:37:03Z, NO BLOCKERS): (B1) the existing sentence that a proof loop re-enters review is scoped to not_reproduced loops, and a proof_grade retry is defined to re-enter proof_verify directly, visit neither review nor fix, and be charged to neither the review-fix budget nor fix's visit cap. (Graph fact) engine visit counters are not populated on the Petri-era engine and proof_verify carries no max_visits, so the proposal's 'while proof_verify's own visit count is below three' could not be realized; the cap is instead a run-recorded proof_grade failure count read by a second command node proof_grade_route, which re-enters proof_verify below three failures and routes to non_converged at the third, so each command node keeps exactly two outcomes as pr_refresh and pr_refresh_head do. proof_verify's entry sentence names proof_grade_route as a second entry. (Advisories) proof_grade is added to the dispatcher.node_timeouts keys; Scenario 195 gains a fenced-verdict case and states the failure counts its cases assume. (Round 3, 2026-10-18T05:02:45Z, NO BLOCKERS) the same edits rebased onto master after another session ratified v155, renumbered to Scenario 195 and revision v156.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T05:02:45Z
verdict: NO BLOCKERS
proposal_stem: proof-record-per-assertion-verdict
content_digest: f7f3e716f78b6c455534960ede0bef0ec1550261ef215bc1bce534bafbed0f66
