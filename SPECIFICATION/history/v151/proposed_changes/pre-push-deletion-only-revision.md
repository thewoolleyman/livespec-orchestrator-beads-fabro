---
proposal: pre-push-deletion-only.md
decision: modify
revised_at: 2026-10-16T20:31:13Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the freeze driver's delegated authority (gitops-fleet-capacity-monitoring, ruling R79 recorded on dfixhe; R66 spec-first self-check for bd-ib-qy5wol.1). No clause of this specification or of livespec-dev-tooling's states the deletion-only pre-push rule. A pure ref-deletion push from the Dispatcher's post-run cleanup runs the full just check aggregate and holds an item's ownership lock 60 to 100 minutes. The refinement keeps the inherited pre-push step order and the always-run ledger-conformance step. The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on these final bytes (re-reviewed on the rebased master after an unrelated revise took v150). A separate read-only Fable reviewer had also returned NO BLOCKERS on the proposal and on these final bytes.

## Modifications

One revise-time modification, from the independent reviewer's non-blocking note: the constraints.md clause gains the sentence "The repository's always-run ledger-conformance pre-push step (`02-ledger-conformance`) is a separate step this skip does not reach: it MUST still run on a deletion-only push, so the skip MUST live inside `just check-pre-push` and never at the lefthook level." immediately before its Scenario 188 pointer. Everything else is the proposal verbatim.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T20:31:11Z
verdict: NO BLOCKERS
proposal_stem: pre-push-deletion-only
content_digest: cba620670b3b61c0b844451c0a21e06ed4bfee527bd076793678d9ab31c2c4bf
