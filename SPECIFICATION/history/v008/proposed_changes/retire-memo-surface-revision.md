---
proposal: retire-memo-surface.md
decision: accept
revised_at: 2026-06-20T16:54:03Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

W7 step 3 (work-item livespec-kfiz): remove the memo surface family-wide. Memo was the lone Transient-category instance; the work-item ledger absorbs it. Drops the capture-memo/process-memos/list-memos contracts, the Memo beads-issue mapping, memo terminology, memo append-only/no-deletion/persistent-knowledge clauses, and Scenarios 2 and 3. The ten-skill surface collapses to a seven-skill surface (4 heavyweight + 3 thin-transport). The lessons reflector and the .ai/ Persistent Agent Knowledge slot are preserved (distinct from the memo surface). heading-coverage co-edit: drops the three memo H2 entries, renames the ten-skill->seven-skill H2, and updates the Scenario-8 clauses[] gap-id (gap-mgtc67l3->gap-55i6toie) which shifted because the gap-detectable intake clause text dropped its process-memos mention.

## Resulting Changes

- spec.md
- contracts.md
- constraints.md
- scenarios.md
- ../tests/heading-coverage.json
