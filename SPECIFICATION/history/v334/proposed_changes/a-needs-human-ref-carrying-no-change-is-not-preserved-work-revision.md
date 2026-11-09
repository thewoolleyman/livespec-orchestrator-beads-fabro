---
proposal: a-needs-human-ref-carrying-no-change-is-not-preserved-work.md
decision: accept
revised_at: 2026-11-09T16:56:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

Accepted verbatim under delegated decision mode, in the slot legacy-coordinator-agent ruled (v334, session 546979bb, 2026-11-09). Every quoted anchor was rechecked on master dc097b277 and matches exactly once. The change adds the READ-side complement of the existing write-side tree guard: recovery routing MUST NOT seed from, or rank, a needs-human ref whose tip tree equals its merge base's tree, and passed_over_needs_human names the reason no-change. Measured instance: bd-ib-so6fef's needs-human/91744d6f… at 4521d441 carried no change against master and outranked the item's real preserved work. The clause owner, the factory-run-work-preservation plan seat, approved the proposal. The independent read-only sonnet review found no blockers; its notes are non-blocking. Scenario 185 gains two cases and no ## heading changes, so tests/heading-coverage.json needs no co-edit. Carrier: bd-ib-qshcwc gains the no-change Definition-of-Done bullet.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T16:55:41Z
verdict: NO BLOCKERS
proposal_stem: a-needs-human-ref-carrying-no-change-is-not-preserved-work
content_digest: 7ad02509ab2a5aabef305aa2a01ed7a80e8c4c7ba1498b72c763f5ec58fe400e
