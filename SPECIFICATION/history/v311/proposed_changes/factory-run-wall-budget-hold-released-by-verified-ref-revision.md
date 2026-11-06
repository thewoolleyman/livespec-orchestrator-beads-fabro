---
proposal: factory-run-wall-budget-hold-released-by-verified-ref.md
decision: accept
revised_at: 2026-11-06T00:00:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Adopted by the maintainer on legacy-coordinator-agent's recommendation ("re: 3 save-before-cancel - ok adopt on your recommendation", recorded on livespec-dev-tooling-6tgd2z at 2026-11-05T23:54:15Z) for bd-ib-l77jxo under plan factory-run-work-preservation (scope events frwp-adopt-l77jxo-2026-11-06 and frwp-l77jxo-design-correction-2026-11-06). A held whole-run wall-budget cancel releases once a remote ref listing verifies a preservation ref holding the run's committed tree; with no verified copy the run is not cancelled and one named needs-human escalation is recorded at the third consecutive held poll. Preserve-before-cancel is unchanged. Independent ratification review (sonnet): NO BLOCKERS; its non-blocking note that escalation on a poll whose ref listing failed is unspecified is left for the implementing item's Definition of Done.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T23:58:58Z
verdict: NO BLOCKERS
proposal_stem: factory-run-wall-budget-hold-released-by-verified-ref
content_digest: cc3be971344e3c4b4fb1bfb25505be0097c546c478da54085b67b093581854a1
