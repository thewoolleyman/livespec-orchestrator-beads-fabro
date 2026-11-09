---
proposal: host-judgement-spend-journal-final-usage.md
decision: accept
revised_at: 2026-11-09T04:48:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written under delegated decision mode, in the v329 slot that legacy-coordinator-agent assigned. The host judgement spend journal (_host_judge_spend_journal.py, commit 5c843b30d, from a factory run with no ledger item) was unspecified behaviour. bd-ib-st2sby's preflight refused it because its References line could only name Scenario 280, which governs caller labelling. The clause extends the existing Host model-judgement caller labelling subsection, which already defines the spawn and the caller vocabulary the journal's name carries. It states the header (including final_usage_line), the assistant lines, the closing result line carrying the result event's usage unchanged with message_ids and no started_at key, the no-result case, and both launch paths. Scenario 332 exercises it. The spec leads the implementation by design: the current code already writes the header fields, naming and fallback the clause states, and bd-ib-st2sby implements the result line and the header flag. No design record is contradicted. The independent sonnet review returned NO BLOCKERS on these exact bytes. Its two nits are left for a later pass: name the input-bound paragraph, and the journal directory is defined only in prose. The proposal's side observation (callers spec_change_tier_gate and groom_spec_change_classification missing from the subsection's caller list) stays with reconciliation batch bd-ib-76ztny. The heading-coverage TODO row and its debt-register entry are owned by bd-ib-st2sby, as the proposal requires.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T04:47:23Z
verdict: NO BLOCKERS
proposal_stem: host-judgement-spend-journal-final-usage
content_digest: 5740ea94e47440b0bfad0d7cd7b82ac66bef3ac51bb2560ee8237e129a9f332d
