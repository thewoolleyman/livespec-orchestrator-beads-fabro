---
proposal: pr-refresh-merged-publication.md
decision: modify
revised_at: 2026-10-26T16:16:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under coordinator ruling R35 (gitops-fleet-capacity-monitoring), which routes the spec arc of work-item bd-ib-hu67v5 (plan bd-ib-ku7phe) through propose-change and a delegated revise. Modified after independent review pass 1 returned two blockers: the unproven-merged-head rule now states the acceptance proof leg's outcome explicitly (every factory_captured assertion UNOBSERVED, yielding NEEDS_ATTENTION, unless a proof record names the merged head; a verified record on another head never passes it; the human-attested and host-captured legs are unchanged), and the merged-reconcile ending is scoped to pr_refresh's first branch query before any rebase, push or disarm, so a branch found absent after a rejected push keeps the cause the rest of the section names.

## Modifications

Scoped the trigger to the first publish-branch query before any mutation, leaving post-push absence (including the rejected-push re-read) to the rest of the section; replaced 'the acceptance pass judges that head only from proof records that already name it' with an explicit proof-leg rule (UNOBSERVED / NEEDS_ATTENTION, no cross-head pass, other legs unchanged); Scenario 248's unproven-head case asserts the NEEDS_ATTENTION verdict, and a fourth case covers a branch found absent after a rejected push.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T16:16:27Z
verdict: NO BLOCKERS
proposal_stem: pr-refresh-merged-publication
content_digest: a67cd2948aafe474ab117dbe60c79e9e0ecb032ea77f141ac5a87b024a1fc9ad
