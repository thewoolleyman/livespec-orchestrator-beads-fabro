---
topic: heavyweight-shared-prose-decomposition
author: p3bspec
created_at: 2026-06-23T03:55:49Z
---

## Proposal: heavyweight-shared-prose-decomposition

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md

### Summary

Adopt the shared-prose decomposition for the orchestrator's five heavyweight ops (capture-impl-gaps, capture-spec-drift, capture-work-item, implement, groom): each op's orchestration moves to a SHARED, harness-neutral prose artifact at .claude-plugin/prose/<op>.md that both the Claude Code and Codex SKILL.md bindings read thin, mirroring livespec CORE's prose + thin-Driver-binding architecture. This is a pure spec/architecture amendment with ZERO behavior change; it also reconciles the heavyweight-skill count to FIVE and folds groom into the heavyweight membership.

### Motivation

The spec is internally contradictory. constraints.md §"Skill orchestration constraints" (first bullet) mandates heavyweight orchestration "lives in the SKILL.md prose," while the same file's Codex-support bullet forbids Codex bindings from "copying Claude-specific SKILL.md bodies." Since the heavyweight bodies ARE the orchestration, you cannot give those ops a Codex binding without copying — unless the orchestration moves to shared harness-neutral prose that both runtimes bind thin. This change adopts that shared-prose model (the same decomposition livespec CORE uses for its prose/<op>.md + thin Driver bindings, per livespec/SPECIFICATION/spec.md §"Contract + reference implementations architecture"), resolving the contradiction. Separately, the spec carries three inconsistent counts for the heavyweight surface — the contracts.md header and consent-discipline section say "(4)"/"four", there are actually five wrapperless authored heavyweight ops (groom being the fifth, previously catalogued only under §"Skills — augmented versus new"), and the SKILL.md descriptions say "(6)". This PR reconciles the SPEC to FIVE; the SKILL.md "(6)" descriptions are fixed in a later refactor PR and are out of scope here.

### Proposed Changes

Four spec edits, no behavior change, no new ## H2 heading, no new scenario:

EDIT 1 — constraints.md §"Skill orchestration constraints", first bullet. Replace the bullet mandating SKILL.md-resident orchestration with: heavyweight skills (capture-impl-gaps, capture-spec-drift, capture-work-item, implement, groom) carry their orchestration logic as a SHARED, harness-neutral prose artifact at .claude-plugin/prose/<op>.md — the consent flow, the multi-step dialogue, the livespec_orchestrator_beads_fabro.* package calls, and the JSON/handoff semantics — and each per-runtime SKILL.md is a THIN binding that resolves the plugin root, reads prose/<op>.md in full, and maps its harness-neutral vocabulary to the runtime's tools, adding no operation behavior of its own; this mirrors livespec CORE's prose + thin-Driver-binding decomposition; thin Python helpers MAY exist for utilities; no dialogue logic is duplicated across the Claude and Codex bindings.

EDIT 2 — contracts.md §"Heavyweight authored skills (4)" heading. Rename heading to "Heavyweight authored skills (5)" and add a framing paragraph stating each heavyweight op decomposes into (a) the shared .claude-plugin/prose/<op>.md artifact and (b) thin per-runtime SKILL.md bindings (Claude + Codex), mirroring core's architecture; name the five heavyweight ops; and represent groom as the fifth heavyweight op via an explicit cross-reference to §"Skills — augmented versus new" and §"Grooming and slice-size calibration" (no new ## H2 is added; the existing #### capture-* subsections are not separate heading-coverage rows).

EDIT 3 — contracts.md §"Store-write consent discipline". Change "four heavyweight SKILL.md front-ends — capture-impl-gaps, capture-spec-drift, capture-work-item, implement" to FIVE front-ends adding groom (groom is a consented store-writer via file_approved_slices / regroom.exit_regroom; its approve-then-file step obtains maintainer approval before the write). Note each front-end's consent flow now lives in the shared prose artifact.

EDIT 4 — contracts.md §"Skills — augmented versus new". Keep groom as the one NEW front-end, but add a clause noting it is ALSO a heavyweight authored skill (the fifth), so its orchestration follows the same shared-prose + thin per-runtime SKILL.md decomposition as the other four; "new" describes its place in the inventory, not a different binding shape. The restraint-budget paragraph is left undisturbed.

Count reconciliation: the SKILL.md "(6)" descriptions are NOT touched here (out of scope; fixed in the later refactor PR). No scenarios.md edit (zero behavior change; existing scenarios stay true).
