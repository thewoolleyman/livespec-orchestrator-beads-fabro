---
proposal: factory-spend-telemetry-carriers.md
decision: modify
revised_at: 2026-11-01T21:31:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

All three proposals carry measured telemetry gaps the factory-spend-accuracy plan needs closed (work items bd-ib-3k3nxw, bd-ib-t7yjrb, bd-ib-welwbc). Each lands in the orchestrator's own contracts under the section that already owns that vocabulary, and each adds a Gherkin scenario. The independent review's first pass found two blockers, both fixed in the modifications. Its second pass returned NO BLOCKERS. Two non-blocking notes remain open: succeeded-vs-rework precedence after a merge, and failed-vs-abandoned for a started run that is reaped. Both are left for a follow-up critique, because the Scenario Outline already fixes the rework-after-merge case.

## Modifications

Proposal 2's clause now names the host-owned enrichment stage as the actor. It sources the values from the usage block's cache_creation.ephemeral_5m_input_tokens and ephemeral_1h_input_tokens, and defines the both, one-only and neither cases. Scenario 293 gains a one-lifetime scenario. Proposal 3 defines an attempt as one run on one ACP fallback-chain candidate, states that the outcome is the final disposition (rework beats failed), and scopes livespec.dispatch.unavailable_fields to the span that omits the value. Scenario 294 gains a Scenario Outline covering cancelled, failed, rework and abandoned, plus an unobservable-model scenario.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T21:30:27Z
verdict: NO BLOCKERS
proposal_stem: factory-spend-telemetry-carriers
content_digest: c04ced299aa0057bd88e4e2626f9498a5dd0d36c6eff33be76dfa7d6a3f10e2b
