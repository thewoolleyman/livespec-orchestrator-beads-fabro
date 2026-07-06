---
proposal: orchestrate-to-drive-rename-and-next-asymmetry.md
decision: accept
revised_at: 2026-07-06T10:39:46Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

SP1 of the needs-attention epic, maintainer-authorized. Renames the operator skill orchestrate->drive as a pure executor of the action-id grammar; retires orchestrate plan and the bare interactive walkthrough (composition relocates to the future needs-attention read surface; the interactive loop to the console); makes spec-side actions non-drive-executable; documents the next scope-asymmetry so no caller rebuilds the incomplete two-next composition. Independent Fable review passed NO-BLOCKERS; two cosmetic polish folds (arrow notation, factory_safe producer note) already landed on the proposal. Applied across contracts.md, constraints.md, spec.md, scenarios.md, README.md, with the tests/heading-coverage.json co-edit (Scenarios 17/21/31 heading fields; Scenario 17 test reset to TODO for the retired bare walkthrough).

## Resulting Changes

- contracts.md
- constraints.md
- spec.md
- scenarios.md
- README.md
- ../tests/heading-coverage.json
