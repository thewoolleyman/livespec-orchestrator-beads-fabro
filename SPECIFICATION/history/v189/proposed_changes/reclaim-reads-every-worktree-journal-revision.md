---
proposal: reclaim-reads-every-worktree-journal.md
decision: modify
revised_at: 2026-10-21T15:55:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 6). Work-item bd-ib-ewdqub, measured 2026-10-16: run 01M51PPR6VVT (bd-ib-tixpma), dispatched from a secondary worktree, failed at publish_draft because the item's publish branch carried a prior run's head from a dispatch journaled in the primary checkout, and the publish-branch reclaim that exists for exactly this case did not run because it read only the dispatching checkout's journal. An earlier dispatch is now a record in the dispatch journal of ANY worktree sharing the repository's git common directory, and an unreadable worktree journal holds with the new reason journal-unobservable rather than reading as no earlier dispatch. Modifications beyond the filed proposal: the held-reason enumeration of "Every arm that cannot measure holds, and says so" gains journal-unobservable, so the reason the bullet introduces is one the hold rule names; and Scenario 225's first case names the preserved-publish ref, the ratified preservation ref, rather than a "run-scoped ref"; and Scenario 144's first-dispatch case, which premised an earlier dispatch absent from this checkout's journal alone, now premises it absent from every worktree's readable journal. Scenario 225 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, found the Scenario 144 conflict as the one blocker in round 1, and after the fix returned NO BLOCKERS on the exact resulting bytes in round 2. Scenario 225 gains coverage and debt entries owned by bd-ib-ewdqub. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Stale publish-branch reclaim before a re-dispatch': bullet 'Only a re-dispatch asks.' defines an earlier dispatch as a record in the dispatch journal of any worktree sharing the repository's git common directory, keeps a dispatch journaled only on another host invisible, and holds an unreadable worktree journal as publish-branch-reclaim-held with reason journal-unobservable naming the path; bullet 'Every arm that cannot measure holds, and says so.' lists journal-unobservable among the hold reasons. scenarios.md: Scenario 225, 'The publish-branch reclaim finds an earlier dispatch journaled in another worktree', whose first case names the preserved-publish ref. Scenario 144's first-dispatch case premises no earlier dispatch in the journal of any worktree sharing the git common directory, with every such journal readable.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T15:55:26Z
verdict: NO BLOCKERS
proposal_stem: reclaim-reads-every-worktree-journal
content_digest: 4e1d802bd04689d82fe4d8aab3e7e59c2ab9358d7e563beb3548a37f8a36de23
