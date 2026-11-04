---
proposal: host-judgement-credential.md
decision: modify
revised_at: 2026-10-20T16:31:58Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fabro-currency (session 5c3e43cb)
---

## Decision and Rationale

Accepted with modification under this repository's delegated revise_decision_mode (.livespec.jsonc spec_governance), by session fabro-currency, routed by fleet coordinator gitops-fleet-capacity-monitoring as R324/R326 under R202. The pre-admission Definition-of-Done judgement started its host judge with the inherited environment. On 2026-10-20 the wrapper's unnumbered CLAUDE_CODE_OAUTH_TOKEN was the account at its weekly limit while the account-selection process had selected another account (dispatcher.py claude-cred-status: CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5 usable, HTTP 200), so every filing that afternoon recorded judge-command-failed. The clause states that host-side judgements authenticate as a dispatch would, using the selected account, else the unnumbered credential with the fallback stated on stderr. It changes no admission gate, headroom rule or verdict-reuse rule. The implementing work-item is bd-ib-y4pyji; the stopgap host preflight received the same fix in PR 3394. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 2. The Step 3.5 stale-branch precondition was skipped with --skip-stale-branch-check: its two findings, spec/propose-lockstep-batch-2 and spec/reprove-merged-item-v2, are other sessions' unlanded proposal branches that touch neither changed section.

## Modifications

One repair from ratification-review round 1, which found the two added Gherkin cases covered only the pre-admission phase although the clause also governs pre-dispatch, and omitted a published selection whose credential is absent. Both cases became Scenario Outlines over the pre-admission and pre-dispatch phases, and the fallback outline gained the selected-but-absent case, using the reviewer's exact text re-indented to the file's two-space Gherkin indent. The contracts.md sentence is unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T16:31:12Z
verdict: NO BLOCKERS
proposal_stem: host-judgement-credential
content_digest: c423a80d329ff7d80dd9021dd96bc0cb0a70b7e76f99f096cb7bcc81538e3fba
