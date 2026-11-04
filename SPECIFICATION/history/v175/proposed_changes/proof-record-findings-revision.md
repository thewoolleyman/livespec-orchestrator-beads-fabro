---
proposal: proof-record-findings.md
decision: modify
revised_at: 2026-10-20T18:15:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fabro-currency (session d8087064)
---

## Decision and Rationale

Accepted with modification under this repository's delegated revise_decision_mode, by session fabro-currency (d8087064), routed by fleet coordinator gitops-fleet-capacity-monitoring as R329 and made top priority by R331 for work-item bd-ib-j56cur, whose pre-dispatch preflight refused because the ratified 'proof_capture' paragraph and Scenario 137 routed proof-record findings through review_fix. Runs 01M5CE38SZJW and 01M5CDH2FZSE exhausted review's firing budget on correct code because review_fix cannot repair a captured record. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 3. The Step 3.5 stale-branch precondition was skipped with --skip-stale-branch-check: its findings are other sessions' unlanded spec branches, none of which touches the changed paragraph or Scenario 137 or 20.

## Modifications

Folded in gpt-6-astra round 1 (4 blockers), coordinator R328, and round 2 (2 Gherkin blockers). (1) The self-contained rule covers only programs neither tracked at the record's named commit nor installed tools invoked by name; tracked programs by path and installed tools by name are allowed. (2) A RECAPTURE verdict needs at least one blocking finding, all of them proof-record findings; the first two route to proof_capture, the third to non_converged without entering proof_capture; a clean review keeps the approval route. (3) Recapture verdicts are governed by that bound alone: an exhausted review-fix budget does not pre-empt one, the review cap's needs-human rest and merge_on_review_cap ship edge do not apply, a post-recapture review visit consumes no review-fix round, and review's engine visit limit admits the two laps; mixed verdicts keep the disposition, budget and cap rules; Scenario 20's capped-out cases gain 'the verdict contains a blocking finding about the tree'. (4) Findings reach proof_capture through the engine preamble and the review record, which proof_capture reads when the preamble is empty. (R328) Record currency compares the TREE of the record's named commit with the head under review, so a checkpoint commit that changes no tree never makes a record stale, and no rule may require a record to postdate one. Scenario 137 gains cases for both channels, the empty preamble, an exhausted budget, self-containment, checkpoint currency, a different tree, printed conclusions, both laps after an exhausted budget, the mixed verdict, the bound, and a clean review. No heading changes, so tests/heading-coverage.json needs no edit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T18:14:37Z
verdict: NO BLOCKERS
proposal_stem: proof-record-findings
content_digest: e66d0f52f0601dbcb4c9a7d9e41e189a6d90d9772aa5e3a2f98d64c5ac7a6d19
