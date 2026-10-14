---
proposal: sandbox-hook-time-limits.md
decision: modify
revised_at: 2026-10-14T02:22:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-publish-draft-green-work-loss
---

## Decision and Rationale

Accepted under the maintainer's standing directive of 2026-10-14 to drive plan publish-draft-green-work-loss (epic bd-ib-acrr56) to completion: plan assertion 2 requires a green run's hooks to complete within the agent tool-call and publish_draft limits on a loaded host, and the dod_gate of bd-ib-xi63mq run 01M4VXXDDG4B1A5SDX497TXNVK required a ratified clause for hook reaping and for the over-limit classification before that item can be graded. Five measured instances on hp on 2026-10-13/14 are cited in the proposal.

## Modifications

Three modifications. (1) Numbering: the proposal's Scenario 177 lands as Scenario 177 in this v134 pass, beside refresh-repair's Scenario 176 (v133 / Scenario 175 being the whole-run wall budget). (2) From ratification review round 1 (gpt-6-astra, two blockers): a hook-over-limit event is now defined as a commit or push ended by a limit while a hook run it started was still executing, observed from the hook run's processes, and a timeout before the hook started or after it finished keeps its existing classification. (3) Every event is journaled whether or not the run recovers, but the item's needs-human cause names hook-over-limit only when that event caused the ending; two negative scenarios cover a push timing out after its hook finished and a recovered event followed by an unrelated stop. Round 2 returned NO BLOCKERS. The refresh-repair decision in the same pass is applied first, and this decision's resulting files carry both revisions cumulatively.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-14T02:12:30Z
verdict: NO BLOCKERS
proposal_stem: sandbox-hook-time-limits
content_digest: d9b5bbf5daceb487c679bcc996df9f59713d882e9f1844b4822b2aea5a2f550b
