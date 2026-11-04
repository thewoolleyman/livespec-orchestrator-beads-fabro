---
proposal: materialized-workflow-dir-name.md
decision: modify
revised_at: 2026-10-26T17:48:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under coordinator ruling R40 (gitops-fleet-capacity-monitoring, high priority), which routes this spec-first change so work-item bd-ib-5y25l2 has a governing clause: every dotted work item is undispatchable because its materialized workflow directory name carries the dot. Modified after independent review pass 1 (NO BLOCKERS) noted that naming both engine commands would make the governing text match the item's first assertion exactly.

## Modifications

The paragraph and Scenario 250 now name both fabro validate and fabro run as the commands under which the engine must resolve the materialized directory.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T17:48:32Z
verdict: NO BLOCKERS
proposal_stem: materialized-workflow-dir-name
content_digest: e7ca93a8f493078e87198bc1d104712b73e78b8576aa54ba34abb6794898a2eb
