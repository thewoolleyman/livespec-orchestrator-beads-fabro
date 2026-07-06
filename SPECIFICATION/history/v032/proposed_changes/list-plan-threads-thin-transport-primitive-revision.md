---
proposal: list-plan-threads-thin-transport-primitive.md
decision: accept
revised_at: 2026-07-06T21:13:51Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept the OR2 spec sub-slice: add list-plan-threads as the fourth thin-transport primitive (a pure read-and-emit enumerator of open, unarchived plan/<topic>/ threads, sibling of list-work-items), and sweep every restatement of the thin-transport count/set. Independently reviewed VERDICT NO-BLOCKERS. Applies exactly the proposal items A-I: contracts.md count bump + section-heading (3->4), the new #### list-plan-threads subsection, the next scope-asymmetry forward-reference naming, the out-of-scope query-only set; constraints.md zero-orchestration set; SPECIFICATION/README.md required-content inventory; the new Scenario 42; and the tests/heading-coverage.json Scenario 42 co-edit.

## Resulting Changes

- contracts.md
- constraints.md
- README.md
- scenarios.md
- ../tests/heading-coverage.json
