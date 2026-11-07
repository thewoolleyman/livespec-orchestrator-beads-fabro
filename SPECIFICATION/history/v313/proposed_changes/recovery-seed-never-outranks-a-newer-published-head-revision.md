---
proposal: recovery-seed-never-outranks-a-newer-published-head.md
decision: modify
revised_at: 2026-11-07T14:17:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session a37283d5) under R301 delegated authority on 2026-11-07: ACCEPT MODIFY on the third revision (content digest 25c4afea...). This is the coordinator's decision, not the maintainer's. The maintainer approved starting this work ('OK start these', recorded on livespec-dev-tooling-6tgd2z at 14:04:11Z). Basis: dropping part (2) is right, because the existing stale-reclaim rule already preserved the measured livespec-dev-tooling-phakbp head at refs/livespec/preserved-publish/livespec-dev-tooling-phakbp/d7f6cd37c, and part (2) conflicted with 'routing MUST NOT mutate'. Narrowing 'cannot tell, so held' to items with a competing ref stays fail-safe and holds only where attribution decides the order. Ranking a stale-reclaim preserved-publish ref as the head it preserves closes the false-competitor case. Independent ratification review (sonnet, read-only): the first two drafts were BLOCKED, and the third revision is NO BLOCKERS. Its non-blocking notes are carried to bd-ib-so6fef: a failed-checkpoint ref whose livespec-preserved-tree comment failed to write ranks as a reclaim ref; no case covers the hold for an unattributed failed-checkpoint ref. Root-fix work item bd-ib-so6fef, plan factory-run-work-preservation (epic bd-ib-nckst7).

## Modifications

Part (2) of the proposal, preserve a non-ancestor publish head before reclaim, is dropped. contracts.md 'Stale publish-branch reclaim before a re-dispatch' already pushes a dead run's head to refs/livespec/preserved-publish/<item>/<head> before deleting the branch and holds on failure; the measured livespec-dev-tooling-phakbp head d7f6cd37c is on origin at that ref. An execution-time hold would also conflict with 'routing MUST NOT mutate'. The run-age bound (part 1) is kept and tightened after independent review. A needs-human ref's run comes from its name or the existing run-trailer rule; a failed-checkpoint preservation ref's run comes from its livespec-preserved-tree comment; the head's run comes from its publication or journal record. The publishing-run-unobservable hold applies only when a competing needs-human or failed-checkpoint ref and a published head are both present. A stale-reclaim preserved-publish ref ranks as the head it preserves. Runs are ordered by journaled dispatch order. The checkpoint-preservation paragraph and the seed-record sentence point at the bound. Scenario 323 is retitled to the run-age bound alone, with seven cases.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T14:17:31Z
verdict: NO BLOCKERS
proposal_stem: recovery-seed-never-outranks-a-newer-published-head
content_digest: 25c4afeadf559f8a25dc52e50e39be2374b6d9e0cba03d0ff749a47fc1a2f818
