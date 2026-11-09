---
proposal: the-committed-fleet-launcher-lacks.md
decision: modify
revised_at: 2026-11-09T22:19:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications. Both proposals port gates that the dispatcher seat's uncommitted launcher runs on every launch and that section 'Provisional fleet launch scripts' does not yet state: the tenant credential wrapper, the origin-tip checkout gate, paced early-exit re-tickets with the goal-minijinja-preflight stop, ACP overrides and the judge-model pass-through, the seat running the committed launcher, and the gmktec hold's one-shot allowlist and priority-1 release. They are the parity gate of the bd-ib-x7bwug cutover (bd-ib-4xqmqh). The new scenario takes number 338 because 329 is taken.

## Modifications

1. Added to the 'Bounded ready-set retry' bullet: a ready-set refusal lists as open blockers only dependencies whose status is neither closed nor done, because the beads projection reports a closed item as done, and the admit decision does not change. Added one matching harness case. This is bd-ib-3ufx6l Definition of Done bullet (b), decided by gmktec-factory-placement on 2026-11-09 at 17:09:37Z with no objection from the coordinator; it ports legacy-dispatcher-agent's ready-set-check.py hand fix. 2. In the gmktec hold's 'Held queue head skipped' sub-bullet, the allowlist exception now covers only the skip that rule adds. An allowlisted item's ticket that carries a held= or wip-wait=1 marker for any other rule is still skipped, as 'Yielding ticket marked and skipped' (from the-committed-fleet-launcher-lacks-2) requires. This resolves a conflict between the two rules that the draft review found. 3. 'Neither that terminal line nor that comment MUST carry' is reworded as 'That terminal line and that comment MUST NOT carry', the correct BCP14 negative. 4. The proposal's new scenario is numbered 338, not 329, because 329 was taken by an earlier revise. 5. The judge-model clause's citation of the bold paragraph lead 'Host judgements take the resolved dod_gate chain' is written as 'the contracts.md paragraph that begins ...' instead of section-sign syntax, because that lead is not a heading and this repository's doctor-no-cross-spec-reference check refuses a section citation that does not resolve to a heading. 6. After the pre-merge LLM doctor phases (high finding 3): the seat-launches-through-the-committed-launcher rule names both committed launchers (impl through dispatch-dual.sh, resume through resume-capped.sh). It takes effect only at the launcher cutover recorded under bd-ib-4xqmqh, once the committed launchers carry every gate the interim launcher runs, the homelab-worker-arm64 route and count included. The cutover drains every live interim launcher before the first committed launch, because the interim queue reader honours only wip-wait=1 markers. The forward reference 'Until that deletion' now reads 'Until the deletion the next paragraph requires'. 7. The tenant wrapper runs nested inside the family wrapper with BEADS_DOLT_PASSWORD unset between them, which is what the interim launcher does; a credential_wrapper whose argv names the family wrapper itself runs as declared, without nesting. 8. The allowlist lock is a flock lock file whose path is a host value in config.sh. 9. The consecutive-early-exit count persists in a per-item state file under a config.sh directory and resets when a run lists. 10. The origin default branch is read with git ls-remote --symref origin HEAD, with no fallback to a literal name, and a failed read is a non-run exit cause. 11. After a second pre-merge doctor pass: Scenario 338's wrapper And-line and the harness case now say each command runs under the tenant wrapper nested inside the default wrapper with the family BEADS_DOLT_PASSWORD absent from the tenant wrapper's environment, matching item 7, where they previously said 'not under the default wrapper'.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T22:19:09Z
verdict: NO BLOCKERS
proposal_stem: the-committed-fleet-launcher-lacks
content_digest: 96af8f7e5104e3fe8276796afb753582fc591a98d37da329cb6ce54783e307d6
