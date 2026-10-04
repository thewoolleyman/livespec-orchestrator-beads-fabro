---
proposal: definition-and-proof-of-done-repair.md
decision: modify
revised_at: 2026-10-04T05:51:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1 (definition-and-proof-of-done)
---

## Decision and Rationale

Accept all seven proposals together, modified by an independent adversarial critique (8 blocking, 21 should-fix, 7 notes) whose findings are accepted. Realized: a plan-level Definition of Done and Proof of Done with carrier-map scope events and a third (proof) archive leg plus a new plan_close_proof conformance check; the host_captured proof mode with host_recorded / host_verified / host_not_reproduced records, an independent replay whose identity is computed by the posting primitive, an accept-valve hold and a reconcile-merged re-run; behavioural assertions with test-existence assertions reported by the gate and suite-only proof refused at capture and review; published sandbox capabilities checked in both directions; the referenced scenario governing the proof; Definition-of-Done authoring rules and findings display in the filing front-ends; proof findings as the fix stage's work order with a not_captured record; a recorded parking verdict with an honest dispatch result; the pointer written whenever a verified record exists; and attribution of a record to the merging dispatch under either of its run identifiers. Scenarios 135-141 added; tests/heading-coverage.json and tests/heading-coverage-debt.json co-edited with seven owned TODO rows naming epic bd-ib-7sjdzv until the implementing children are filed. Motivating evidence: plan/definition-and-proof-of-done/research/004-reopen-failure-analysis-and-repair-scope-2026-10-04.md.

## Modifications

Relative to the filed proposal: (1) the Definition of Done body grammar, the default-mode sentence, the human_attested definition, the deliverable policy, the PASS bullet, the ai-only bullet, Unevidenceable assertions, the stale-pointer rule, the asset-name form, the archive transfer passages, seam (1) and the Planning Lane restraint budget are amended IN PLACE so no ratified sentence contradicts the new rules; (2) plan_close_evidence is unchanged and a new plan_close_proof check applies only to epics closed after 2026-10-04; (3) scope events gain a carriers: block and only carrier-map events are refused when incomplete or void a proof; (4) the primitive takes subject=plan for an epic (bare bullet is host_captured, zero or one reference line); (5) host record verdict words are host_recorded, host_verified, host_not_reproduced; (6) the accept valve refuses a pending host leg and the posting primitive drives reconcile-merged, whose precondition now admits an item resting in acceptance; (7) suite-only proof is a blocking review finding and proof_verify meeting one ends needs-human rather than not_reproduced; (8) only mechanical findings withhold ready at filing, test-existence and scenario-reference findings are advisory; (9) an unpublished capability set is UNKNOWN and withholds only the missing-capability finding; (10) a NEEDS_ATTENTION parking reports status needs-attention with existing exit code 1, one ledger comment per distinct verdict and pending-leg set; (11) capabilities, filing and scenario-governed proof get their own headings (Scenarios 139, 140, 141) instead of extending existing ones; (12) a record's run identifier may be the Fabro run id or the dispatch id the Dispatcher declared, measured on bd-ib-mxqrr4.

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
reviewed_at: 2026-10-04T05:51:19Z
verdict: NO BLOCKERS
proposal_stem: definition-and-proof-of-done-repair
content_digest: 43fbb46219759f3264fe62a155763ea5f34e38b7520c962b6bfb602ec58f54eb
