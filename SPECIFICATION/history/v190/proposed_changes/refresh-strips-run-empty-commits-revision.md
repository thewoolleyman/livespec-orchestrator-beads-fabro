---
proposal: refresh-strips-run-empty-commits.md
decision: modify
revised_at: 2026-10-21T16:13:00Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 6). Work-item bd-ib-reapbq (plan fabro-currency, bd-ib-6tcjfx), released from pending-approval on 2026-10-16 under the maintainer's scope event on livespec-dev-tooling-dfixhe: its Definition of Done requires a run's empty engine checkpoint commits to be dropped before publication, and it cannot pass a dod_gate while the ratified sentence says an unchanged head proceeds untouched. When the published head already contains the default branch and carries any of the run's own empty commits, pr_refresh republishes it without them under the paragraph's explicit lease, the rewrite takes the carried_forward decision without re-proving, and a head carrying none is not republished. Modification beyond the filed proposal: one clarifying parenthetical defining the run's own empty commits as commits the run itself created that change no tree, such as engine checkpoint commits, matching the ratified proof-record rule that a commit changing no tree never makes a record stale; and Scenario 226's second case states that the untouched head proceeds to pr, the clause's own outcome, rather than that the verified proof still names the published head. Scenario 226 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 1. Scenario 226 gains coverage and debt entries owned by bd-ib-reapbq. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Definition-of-Done and Proof-of-Done stages', paragraph 'Scripted publication and proof-head integrity.': the sentence 'An unchanged head proceeds to pr.' gains the filed exception: when the default branch is already contained in the published head and that head carries any of the run's own empty commits (defined as commits the run itself created that change no tree, such as engine checkpoint commits), pr_refresh republishes it without them under the paragraph's explicit lease, the rewrite takes carried_forward and does not re-prove, and a head carrying none is not republished. scenarios.md: Scenario 226, 'An unchanged refresh strips the run's empty commits and carries the proof forward'. Scenario 226's second case states the head proceeds to pr.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T16:12:39Z
verdict: NO BLOCKERS
proposal_stem: refresh-strips-run-empty-commits
content_digest: 4f8c2986fe3c476a8d2a02651d824cac753dc243b1fe2f4ff99aa53c12733e6e
