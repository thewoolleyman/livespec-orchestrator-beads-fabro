---
topic: planning-lane-realization
author: claude-opus-4-8
created_at: 2026-06-25T10:28:49Z
---

## Proposal: Planning Lane realization: the plan front-end

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

Add plan as the SIXTH heavyweight authored skill and a new contracts.md section Planning Lane realization that realizes livespec's repo-agnostic Planning Lane guidance (the same cut as grooming). Covers the plan create/resume API (no-arg interactive create-or-resume with a canonical confirmed slug; plan <slug> strict resume-or-fail), the plan/<topic>/ thread store (one reserved handoff.md plus zero-or-more research notes), the two one-directional seams and the no-shadow-ledger rule, the handoff self-sufficiency gate (cold-open readiness test, one-path, no-dangling-reference), archive-on-epic-close, and a restraint budget. Updates the heavyweight count (5->6), the store-write consent discipline (plan is a consented store-writer via capture-work-item), the cross-references to the heavyweight section name, and the constraints.md heavyweight list.

### Motivation

livespec-zs22 increment 3a (work-items livespec-zs22.5 and livespec-zs22.3): realize the Planning Lane as the reference orchestrator's stateful plan front-end, mirroring how grooming's pattern (core NFR) gained its realization here. The handoff self-sufficiency gate is the realization half of zs22.3 (the pattern half landed in core NFR).

### Proposed Changes

1) contracts.md: rename heading 'Heavyweight authored skills (5)' to (6); add plan to the heavyweight intro list and a sentence naming plan the SIXTH op detailed in the new realization section; add plan to the six heavyweight front-ends in the Store-write consent discipline with a consent note (consented store-writer via the capture-work-item operation); update the two 'per Heavyweight authored skills (5)' cross-references to (6). 2) contracts.md: add a new H2 section 'Planning Lane realization' (parallel to 'Grooming and slice-size calibration') with subsections for the plan front-end API, the plan/<topic>/ thread store, the two seams and no-shadow-ledger rule, the handoff self-sufficiency gate, archive-on-epic-close, and the Planning Lane restraint budget. 3) constraints.md: add plan to the heavyweight-skills orchestration list. 4) tests/heading-coverage.json: add a TODO entry for the new 'Planning Lane realization' H2 (co-edit).
