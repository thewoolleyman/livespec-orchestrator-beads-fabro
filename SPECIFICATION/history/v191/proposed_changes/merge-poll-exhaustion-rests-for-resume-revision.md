---
proposal: merge-poll-exhaustion-rests-for-resume.md
decision: modify
revised_at: 2026-10-21T16:34:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 5). The file carries three proposals; this revise ADOPTS ONLY THE FIRST and re-files the other two, unratified and unrejected, as the new pending topic terminal-claim-remedies-read-the-forge in the same pull request. Proposal 1, work-items bd-ib-l6rleb and bd-ib-ddu6wq (superseding bd-ib-y1b7): a run that succeeded and armed auto-merge left its item active under an ended claim when the merge-poll budget ran out on an open, non-conflicting pull request (measured on bd-ib-3hpdvm, 2026-10-16, and bd-ib-wvj4rk, 2026-10-17). The Dispatcher now re-reads the pull request at expiry, proceeds on MERGED, and otherwise rests the item exactly as the ratified base-advanced-after-arming rest does, with cause merge-poll-budget-exhausted. Why the narrowing: the configured ratification reviewer, gpt-6-astra, in a separate read-only session, found four blockers in round 1, all in proposals 2 and 3: the Status changes bullet of Stranded claim release still names reconcile-runs unqualified; move:<id>:ready from active conflicts with the ratified per-lane operator verb set ("active: observe only") and the door rules; a capacity handoff advertising reconcile-merged can be refused by a live ownership lock, breaking "executable as advertised"; and Scenario 221's merged case omits the exclusion condition. Resolving the verb-set conflict changes the ratified vocabulary of the active lane, which may depart from the design record behind that table and so is not decided in a delegated pass; the re-filed topic carries all four amendments and a decision note for its revise. In round 2, the same reviewer returned NO BLOCKERS on the narrowed resulting bytes, confirming they contain no edit from proposals 2 or 3. Scenario 220 was confirmed free on master and in every pending proposal, and gains coverage and debt entries owned by bd-ib-l6rleb. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

Narrowed to proposal 1. contracts.md, "Armed pull request overtaken by the default branch.": the exhausted-budget sentence is replaced by the filed re-read-and-rest rule with cause merge-poll-budget-exhausted. scenarios.md: Scenario 220 as filed. Proposals 2 and 3 (the resume-refusal remedy and the capacity-handoff forge read) and their Scenarios 221 and 222 are not applied; they are re-filed, amended by the round-1 review findings, as the pending topic terminal-claim-remedies-read-the-forge.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T16:34:17Z
verdict: NO BLOCKERS
proposal_stem: merge-poll-exhaustion-rests-for-resume
content_digest: b09865b74d3f8b2d6a553beaf73daee2df921829477ed793573dbf6bc1d81e6f
