---
proposal: cross-provider-override-replaces-env.md
decision: modify
revised_at: 2026-10-21T10:17:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 12). Work-item bd-ib-5j4b: on run 01M0YVK5KHMH (hp, release 0.82.0, 2026-08-26) this repository's review node, routed to Codex through dispatcher.acp_nodes, rendered ANTHROPIC_MODEL beside a Codex model, because the ratified per-field rule merges env across layers. Modification beyond the filed proposal: the exception is keyed on a more specific layer setting a command that differs from the command the less specific layers resolve to, not on a resolved agent id, because this section states that nothing in the manual form is derived and identity is never inferred from command text, so a manual-form layer has no agent id to compare; a structured entry renders before any merge, so a same-agent structured override renders the same command and keeps merging. A third scenario covers a changed command for the same adapter. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 1; its two non-blocking suggestions (a three-layer example, and qualifying the different-adapter sentence for adapters sharing a launcher command) were not adopted. Scenario 233 gains coverage and debt entries owned by bd-ib-5j4b.

## Modifications

contracts.md: the 'Resolution is per node and per FIELD' sentence gains the changed-command exception (inherited env discarded, only the overriding layer's env applies), stated as a comparison of the rendered command field so it holds for both forms, with the consequence that a same-adapter command change restates its env. scenarios.md: Scenario 233 is titled for adapters rather than agents ('A node routed to a different adapter does not inherit the replaced adapter's env') and carries three scenarios: a changed command discards inherited env, an env-only override merges, and a changed command for the same adapter restates its env.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T10:16:10Z
verdict: NO BLOCKERS
proposal_stem: cross-provider-override-replaces-env
content_digest: 47352dfc15f5120a01a5dfd1cf64fadac1e035829e289a5830f1621e69468900
