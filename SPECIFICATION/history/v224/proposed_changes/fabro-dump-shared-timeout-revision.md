---
proposal: fabro-dump-shared-timeout.md
decision: modify
revised_at: 2026-10-26T11:37:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under coordinator ruling R27 (gitops-fleet-capacity-monitoring, recorded on livespec-dev-tooling-dfixhe), which delegates this spec-first change for work-item bd-ib-exyiqr. Modified after independent review pass 1 returned two blockers: the pointer requirements are now scoped to the preserve-by-reference export (the read-back check and the worker-exit log read keep their own failed-dump handling and share only the bound), and success means an export that succeeds within the bound, not one that merely completes, so a non-zero exit within the bound is still a failed dump.

## Modifications

Scoped the pointer requirements to the preserve-by-reference export; each call site keeps its own failed-dump handling; an export failing by timeout or by non-zero exit within the bound yields the failed-dump pointer; 'headroom of about twice' reworded as 'a timeout approximately twice the measured maximum'; Scenario 247's slow case specifies a zero exit and a successful export.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T11:36:25Z
verdict: NO BLOCKERS
proposal_stem: fabro-dump-shared-timeout
content_digest: b796e6de2cbc26bb945e1ba52a7d7c8b6c30c7b0bfa743d4d43caf283eaa9d4b
