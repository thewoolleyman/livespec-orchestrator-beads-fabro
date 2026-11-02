---
proposal: select-the-target-org-github.md
decision: modify
revised_at: 2026-11-02T08:56:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted in substance. The clause as ratified made the coordinator-ordered placement of homelab on the shared main Petri service unservable (bd-ib-voozdp). The change admits a per-run App selection on a shared server. It keeps the per-tenant route, the fail-closed resolution with no fallback, the ephemeral-token and no-durable-key-in-sandbox rules, and the withheld workflows grant word for word. Decided under delegated mode (coordinator R301); the independent reviewer found one blocker on the first draft, fixed by the modification.

## Modifications

Added a fourth Scenario 32 scenario, 'A malformed github_app declaration refuses before claim naming the key', so the Dispatcher-side MUST refusal of a malformed dispatcher.factories.<name>.github_app declaration carries its own Gherkin scenario. The independent ratification reviewer raised this as a criterion (c) blocker on the first draft. The contracts.md text is unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T08:56:08Z
verdict: NO BLOCKERS
proposal_stem: select-the-target-org-github
content_digest: 883aa778bd3597edde086ed9167705f83d27119a92b9e00887b84dc7ac609827
