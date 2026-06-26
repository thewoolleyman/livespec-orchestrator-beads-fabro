---
topic: interactive-dialogue-ownership
author: claude-opus-4-8
created_at: 2026-06-26T03:36:32Z
---

## Proposal: Interactive dialogue ownership (orchestrator-side)

### Target specification files

- SPECIFICATION/contracts.md
- tests/heading-coverage.json

### Summary

Relocate the `## Interactive dialogue ownership (orchestrator-side)` contract section out of livespec core and into this orchestrator's own contracts.md, since this plugin is the OWNER of the interactive gap/drift consent dialogue and the load-bearing zero-dependency invariant (orchestrator front-ends do not depend on, and must not call back into, the livespec-driver-claude Driver) is verifiable only on the orchestrator side. The existing same-named cross-repo citation in `## Store-write consent discipline` is retargeted from `livespec/SPECIFICATION/contracts.md §"..."` to the new local section. Co-edits tests/heading-coverage.json to map the new heading to the real zero-dependency test.

### Motivation

livespec-besm.6 (RELOCATE decision, maintainer 2026-06-26): clear core's final heading-coverage TODOs by relocating the two genuinely sibling-owned contract sections into the repos that own them, with a real exercising test added at the owner. This is the B2 half. Core's release-gate `check-no-todo-registry` drops one TODO when the paired core-side revise removes this heading.

### Proposed Changes

Add a new `## Interactive dialogue ownership (orchestrator-side)` section to SPECIFICATION/contracts.md (immediately before `## Store-write consent discipline`) stating that the interactive consent dialogue is owned by this orchestrator; the consent-dialogue front-ends (`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`, `groom`) are orchestrator-internal; the Driver does not depend on them and they MUST NOT call back into the Driver; invoking a core operation (e.g. /livespec:propose-change) is permitted because that is core's surface the Driver merely binds. Retarget the `## Store-write consent discipline` citation to the new local section. Add a tests/heading-coverage.json entry mapping the new heading to tests.livespec_orchestrator_beads_fabro.test_interactive_dialogue_ownership.test_consent_dialogue_skills_carry_no_driver_dependency, a real test asserting the front-ends ship their own prose, name no Driver plugin, and the package imports no Driver module.
