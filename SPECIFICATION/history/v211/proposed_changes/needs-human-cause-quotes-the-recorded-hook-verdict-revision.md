---
proposal: needs-human-cause-quotes-the-recorded-hook-verdict.md
decision: modify
revised_at: 2026-10-25T00:40:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accepted in substance, modified to resolve one ratification-review blocker and one note. The clause binds the needs-human cause and the dispatch journal's outcome row to the hook's RECORDED verdict for a refused commit attempt, reusing the refused-attempt definition ratified in v208 ("An implement turn that ends incomplete does not succeed") and the existing hook-over-limit and no-verdict classifications for the cases it excludes, so no classification overlaps. Behaviour is stated as BCP14 clauses with a matching scenario inside Scenario 179, no `## ` heading is added, so tests/heading-coverage.json needs no co-edit. Grounded on run 01M5QNH88NHN68ST28Y80CZJ48 (bd-ib-8zyan), whose recorded tool output carried exit status 1 and the failed target check-types while the agent's text said the hook did not complete. Independent read-only gpt-6-astra ratification review (codex exec -s read-only, separate sessions): pass 1 BLOCKERS (1) plus one note, session 01a1705a-2a92-7231-a8cd-2d66a884f3d5; pass 2 NO BLOCKERS on the exact resulting bytes, session 01a1705c-668f-7710-847b-70f28099c020 at 2026-10-25T00:01:43Z. First cut as v210 (local commit d20f2c092, never pushed); PR 3601 merged as v210 at 00:02:35Z, so this revision was mechanically rebuilt on master bd80f5631 as v211 with byte-identical paragraph and scenario, and pass 3 returned NO BLOCKERS on the exact rebuilt bytes, session 01a1707f-c88d-75c0-ac8f-14924d7e450b at 2026-10-25T00:40:16Z. Decision delegated per spec_governance.revise_decision_mode=delegated with exact-byte evidence; work item bd-ib-k3nmbi, coordinator gitops-fleet-capacity-monitoring on maintainer direction of 2026-10-24.

## Modifications

Two changes against the proposal text, both from the pass-1 independent read-only gpt-6-astra review. (1) BLOCKER: the exclusion sentence ended "keeps the `hook-over-limit` and `no-verdict` classifications above", which assigned classifications that do not cover every excluded case (a commit that exits non-zero before any hook runs is `failed` under the commit-runner contract); it now ends "retains its existing classification under the preceding paragraphs." (2) NOTE: the proposal placed the paragraph immediately after "A commit leg completes past one tool call.", which would have redirected the next paragraph's "The preceding paragraph's end-of-turn rule" reference at the new text; the paragraph is placed after "A commit run outlives a node-timeout cut." instead, leaving that reference intact. The scenario text is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T00:40:16Z
verdict: NO BLOCKERS
proposal_stem: needs-human-cause-quotes-the-recorded-hook-verdict
content_digest: 57eec1a1d18631f19144fa418fe3a9345c36f0d0468a8d85f74ea07760485e5c
