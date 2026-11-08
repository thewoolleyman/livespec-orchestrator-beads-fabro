---
proposal: orchestrator-currency-surfaces-push-agents.md
decision: accept
revised_at: 2026-11-08T21:17:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: the gmktec-factory-placement plan seat (livespec-dev-tooling-me5aqz), which filed the proposal at legacy-coordinator-agent's R301 request and took the revise slot in the coordinator's order (v324, then hfhezo as v325, then this as v326). Carrier: bd-ib-rfhnqf, refused at dispatch on 2026-11-08T00:02:51Z as spec-change tier (verdict partial, linked topic orchestrator-currency-surfaces-push-agents). livespec-dev-tooling spec v155 (livespec-dev-tooling#3734, §"Orchestrator build adoption") makes a fleet clone hold its installed orchestrator build, and makes `just adopt-orchestrator-build` the only way the build moves. This plugin's currency surfaces still treat a held clone as a defect and tell agents to run a raw `claude plugin update`, which routes around that operator step. The proposal brings §"Self-contained plugin dispatch" and Scenarios 95 and 271 in line, and it is applied as filed on post-v325 master (94d98b696). v325 touched only the commit-leg paragraph and Scenario 179, so the two do not overlap. No `## ` heading changes. An independent read-only sonnet reviewer recomputed the digest and found NO BLOCKERS at 2026-11-08T21:16:56Z. Its non-blocking notes: the new fourth Scenario 95 case sits last in the block, and 'release-adoption item' is not defined elsewhere.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T21:16:56Z
verdict: NO BLOCKERS
proposal_stem: orchestrator-currency-surfaces-push-agents
content_digest: e1df5c4391e93b4dd4d62c2f640752833e3bb93bce437ec6afe93002b028dfaa
