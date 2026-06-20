---
topic: retire-memo-surface
author: claude-opus-4-8
created_at: 2026-06-20T16:46:31Z
---

## Proposal: Retire the memo surface

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Remove every memo reference from livespec-impl-beads' SPECIFICATION. Memos were the lone instantiation of the upstream Transient (queue/archive item) category; the reference orchestrators retire that surface (W7 step 3) and the work-item ledger absorbs its function. This collapses the ten-skill surface to a seven-skill surface (4 heavyweight + 3 thin-transport) and drops the capture-memo / process-memos / list-memos contracts, the Memo beads-issue mapping section, the memo terminology, the memo append-only / no-deletion / persistent-knowledge clauses, and the two memo scenarios.

### Motivation

W7 step 3 (work-item livespec-kfiz): the memo surface is being removed family-wide. The core contract (livespec v123) already retargeted the auto-memory redirect from capture-memo to capture-work-item, and core's own spec.md records memo as a retired surface. The four post-kill capture dispositions become: actionable -> the work-item ledger (capture-work-item); discard -> not filed; spec-bound -> /livespec:propose-change (capture-spec-drift already does this); persistent-knowledge -> the orchestrator's own lessons.md home (the lessons reflector is PRESERVED, distinct from the memo surface).

### Proposed Changes

spec.md: drop the **Beads issue (memo)** terminology entry and the trailing 'Memos' parenthetical from the §Terminology adopt-list; rewrite the Purpose / Scope-boundary mentions of 'work-items and memos' to 'work-items'; drop memo from the Materialized-view definition and the Substrate-properties / What-this-spec-is-not bullets.

contracts.md: rename §"The ten-skill surface" to §"The seven-skill surface" and its '(6)'/'(4)' subsection counts to '(4)'/'(3)'; delete the `capture-memo`, `process-memos`, and `list-memos` skill subsections; delete §"Memo beads-issue mapping"; drop memo from the Store-write-consent-discipline front-end list, the consent-by-authorship example, the out-of-scope-surfaces list, the §"Grooming" process-memos references, the `next` work-items-only rationale's memo wording, the Spec-Reader consumers list, the `compat` block's `memos_path` mention, and the Cross-boundary-handoffs list (drop handoff entries 2 and 3 and renumber).

constraints.md: drop memo from the Skill-orchestration-constraints heavyweight/thin-transport lists and the Dispatcher net-new clause; drop the §"Forbidden patterns" 'No memo deletion' bullet; rewrite the Persistent-Agent-Knowledge constraints to remove the process-memos coupling; drop memo from the memo-hygiene mentions.

scenarios.md: delete Scenario 2 (Memo -> spec-bound disposition) and Scenario 3 (Memo -> persistent-knowledge graduation); renumber the remaining scenarios is NOT required by any check, so the remaining scenario numbers are left as-is to avoid churn, and the memo wording in Scenario 5 (doctor cross-boundary read) and Scenario 6 (Layer 3 driver) is rewritten to drop the memo-hygiene / list-memos references.

tests/heading-coverage.json: drop the three memo H2 entries (## Memo beads-issue mapping; ## Scenario 2 — Memo → spec-bound disposition; ## Scenario 3 — Memo → persistent-knowledge graduation) in lockstep.
