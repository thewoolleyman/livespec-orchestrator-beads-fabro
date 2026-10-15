---
proposal: resume-republication-anchor.md
decision: modify
revised_at: 2026-10-15T05:04:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-publish-draft-green-work-loss
---

## Decision and Rationale

Accepted with two clarity edits ruled at revise time by the fleet coordinator gitops-fleet-capacity-monitoring after its Fable review (APPROVE, no blockers). First, condition (b) reads 'the published head the run's terminal checkpoint carries', matching the ratified phrase 'the checkpoint's successful published head' in the Dispatcher successful terminal evidence section, so implementers read the same field. Second, conditions (a) and (d) name publish_draft only: a pr_refresh rebase rewrites commits, so condition (c) cannot hold after it, and the retained refusal sentence about a pr_refresh that rebased and pushed stays true. Decision authority: the maintainer authorized the freeze driver (gitops-fleet-capacity-monitoring) to approve spec revises after a Fable subagent review. That authorization is recorded on livespec-dev-tooling-dfixhe (scope event, 2026-10-15T00:1xZ) and was relayed to this session by the driver; this session did not receive it from the maintainer directly. Independent ratification review: gpt-6-astra, read-only, NO BLOCKERS on the exact final bytes. The first review (2026-10-15T00:30:44Z) covered the same edits on an earlier base. The edits were re-applied unchanged onto master after v138 and v139 landed, and the review was re-run on these final bytes (2026-10-15T05:03:07Z, and again at 05:04:30Z against the digest over SPECIFICATION-relative resulting_files paths). It confirmed the anchor is consistent with v138's carried_forward records and with its rule that a resume from an earlier verified head enters pr_refresh before pr. Non-blocking reviewer notes, recorded for follow-up: extra scenarios could cover failed ancestry and termination outside the permitted window; and the Fable reviewer noted that the motivation overstates today's cancel anchor, which applies only when no proof record carries the dispatch id. The new anchor covers that case too. Implementation: bd-ib-elkb33 (plan publish-draft-green-work-loss, epic bd-ib-acrr56).

## Modifications

Condition (b): 'the head of the run's terminal checkpoint' becomes 'the published head the run's terminal checkpoint carries' (and the matching Scenario 142 Given line). Conditions (a) and (d): 'publish_draft or pr_refresh' becomes 'publish_draft'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T05:04:30Z
verdict: NO BLOCKERS
proposal_stem: resume-republication-anchor
content_digest: a8b395685ece614b7afa56905b831e70572fd07347c93045ca7da216d93779e1
