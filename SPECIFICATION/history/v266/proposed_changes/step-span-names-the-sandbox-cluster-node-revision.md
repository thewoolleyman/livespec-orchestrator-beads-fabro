---
proposal: step-span-names-the-sandbox-cluster-node.md
decision: accept
revised_at: 2026-11-01T13:36:29Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. Plan kubernetes-sandbox-backend assertion 4 needs the node that ran a dispatch named on its run_turn record beside livespec.dispatch.factory. Measured 2026-11-01: the fabro dataset has no cluster-node dimension. Work item bd-ib-motuct is held at spec-change tier against this very heading, and coordinator gitops-fleet-capacity-monitoring ruled that it needs ratification rather than a tier release. The clause is a conditional addition in the same shape as the section's ACP and gate clauses. It uses the OpenTelemetry k8s.node.name convention and scopes the obligation to pod sandboxes, so nothing is fabricated for Docker. Scenario 291 states the behaviour. The independent reviewer found no contradiction. The tests/heading-coverage.json entry for Scenario 291 lands in the same pull request outside the spec tree.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T13:35:56Z
verdict: NO BLOCKERS
proposal_stem: step-span-names-the-sandbox-cluster-node
content_digest: 0fd504d60988316e9a6c9f5b2ce1ec489f2df6bad57be17b7385b089dd3315be
