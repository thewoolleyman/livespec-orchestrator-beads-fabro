---
proposal: merge-hold-release-arms-a-message-only-head-move.md
decision: accept
revised_at: 2026-11-10T09:56:22Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept. The host-side hold release may arm a pull request whose current head differs from the proved head only in its commit message: distinct commits, each with exactly one parent, the same parent, the same tree object. Equal tree on an equal single parent means the merge lands exactly the proved content on exactly the proved base, so the proof still describes what merges, and the forge's required checks still run on the new head. The release reports the proved head, the current head and the shared tree; a different tree, a different parent, a commit without exactly one parent, or an unreadable tree or parent refuses naming the measurement, reporting both heads, with the pull request unarmed. It writes no proof record for the moved head and leaves pr's in-run arming unchanged. Measured case: livespec-dev-tooling#3999 (ef218b75 -> caa9ec00, both tree 5053e2e2, parent a9e9178a), hand-landed after the guard refused. Scenario 184's one merge-hold release scenario becomes four; no H2 heading is added. Work item bd-ib-nceul6.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T09:49:07Z
verdict: NO BLOCKERS
proposal_stem: merge-hold-release-arms-a-message-only-head-move
content_digest: d4a51e18e92321b59fdd7e6a7cbacff6b9a65e0ee0f6c3cbe76154529fdbb608
