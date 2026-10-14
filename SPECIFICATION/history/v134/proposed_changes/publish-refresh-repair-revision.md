---
proposal: publish-refresh-repair.md
decision: modify
revised_at: 2026-10-14T02:22:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-publish-draft-green-work-loss
---

## Decision and Rationale

Accepted under the maintainer's standing directive of 2026-10-14 to drive plan publish-draft-green-work-loss (epic bd-ib-acrr56) to completion: plan assertion 1 requires a janitor-green run whose base moved to publish its work intact, which the ratified fail-closed-on-conflict clause forbade. Research note 001 of that plan measured 8 of the 11 lost runs (33.3 of 44.0 slot-hours) on hp on 2026-10-13 as rebase conflicts or post-refresh gate failures. The fail-closed posture is kept for every cause an agent cannot repair (unreachable origin, foreign head, authentication), and the repair is bounded.

## Modifications

Three modifications, from ratification review round 1 (gpt-6-astra, three blockers). (1) Scenario 132's step 'Publication refuses unverifiable provenance and conflicts' is split: a foreign or changed remote head still fails closed, and a new step states a conflicted pr_refresh is never resolved by the script but takes the refresh-repair route. (2) The restoration target is defined as the stage's pre-refresh head (the head janitor last passed for publish_draft; the recorded published or validated resume-provenance head for pr_refresh, covering resumed runs), and restoration resets the working branch even when the refresh completed and only the gate rejected it. (3) A separate 'Refresh-repair accounting' paragraph fixes when a round is counted, caps rounds at two across both stages, keeps review_fix_cap untouched, counts each pr_refresh refresh (clean or repaired) once toward the three-refresh bound and publish_draft refreshes never, and requires the fix node's visit limit to accommodate the repair rounds; Scenario 175 gains pr_refresh-repair, resumed-run, review-fix-budget and mixed-bound cases. Round 2 returned NO BLOCKERS. (4) Renumbering: PR 2917 ratified v133 and Scenario 175 first, so this revision is cut as v134 and its scenario is Scenario 176 (the proposal text still says 175); every in-text reference was updated, and review round 3 confirmed the re-application on master 35fea321, including that refresh-repair rounds stay inside v133's whole-run wall budget, with NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-14T01:15:35Z
verdict: NO BLOCKERS
proposal_stem: publish-refresh-repair
content_digest: a148da66bea64827626d179d6dca80c406b370a36630c0c2eea023bbf12253fa
