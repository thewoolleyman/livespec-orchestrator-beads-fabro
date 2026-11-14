---
proposal: a-run-routed-fresh-can.md
decision: modify
revised_at: 2026-11-14T00:55:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded PASS and gave the GO for this revise (2026-11-13, orchestrator revise slot after v373). It releases bd-ib-dvv2ge's spec-change-tier hold: a run routed fresh keeps its start commit in every commit it settles and publishes. The write rule it cites, an-operator-preserve-writes-a, is ratified in this same pass.

## Modifications

One grade fix, on legacy-coordinator-agent's grade of #5213 (2026-11-14): the paragraph's parenthetical "(proposed as an-operator-preserve-writes-a)", which followed the quoted title of the paragraph "A writer that finds a run's needs-human ref behind the tree it preserves moves that ref forward rather than writing a second one", is dropped. That proposal is ratified in this same pass, so the parenthetical would name an archived proposal; the provenance is recorded here instead. The text is otherwise as proposed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T00:55:41Z
verdict: NO BLOCKERS
proposal_stem: a-run-routed-fresh-can
content_digest: a99f02fac4279483a5e1e30018113c6f9bdaa20a20e3fba26b66aa821e35c693
