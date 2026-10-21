---
proposal: publish-push-refusal-names-its-cause.md
decision: modify
revised_at: 2026-10-21T15:18:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 6). Work-item bd-ib-35kfra: a refused publish_draft push does not distinguish its three causes (a pre-push hook refusal, a non-fast-forward rejection, an unreachable origin), so triage cannot tell a hook failure from a stale publish branch; freeze-driver ruling R68 held the item because its assertions were ungoverned. The refusal now names its cause, reusing the failed-targets attribution rule for a hook refusal. Modifications beyond the filed proposal: the sentences are placed in "The stages." paragraph immediately after the publish_draft command node's definition, rather than in "Scripted publication and proof-head integrity", which governs pr_refresh and pr; and "its output after the push-failed marker" became "its failure output", because no push-failed marker is defined in the ratified spec. Scenario 224 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes. Scenario 224 gains coverage and debt entries owned by bd-ib-35kfra. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Definition-of-Done and Proof-of-Done stages', paragraph 'The stages.': immediately after the publish_draft command node's definition, a refused publish_draft push names its cause in its failure output: a pre-push hook refusal names the hook's failed targets by the structured-summary rule of 'Failed post-merge janitor target attribution', a non-fast-forward rejection directs reconciling the stale publish branch, and an unreachable origin is named; the node still fails closed before proof_capture. scenarios.md: Scenario 224, 'A refused publish_draft push names the cause that refused it'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T15:17:57Z
verdict: NO BLOCKERS
proposal_stem: publish-push-refusal-names-its-cause
content_digest: 127993b7bb2dadd4f4f3a24edf18bef33f4cb9be675689a8a94d89377f3ce669
