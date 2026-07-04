---
topic: claude-fable-5-critique
author: claude-fable-5
created_at: 2026-07-04T08:04:24Z
---

## Proposal: No-root-research-tree invariant lacks normative force and scenario coverage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The v028 revision of contracts.md section 'The plan/<topic>/ thread store' declares the retirement of the root research/ tree purely descriptively: 'There is NO root research/ tree: standalone analysis lives in a plan thread (or, once the thread closes, under plan/archive/), and a living reference document lives in docs/, .ai/, or a dedicated top-level topic directory (precedent: loop-reflection-gate/).' Restate the invariant with BCP14 normative force (MUST NOT / MUST) and add a scenario exercising the placement behavior, so the clause is gap-detectable and the behavior is covered per the behavior-implies-clause-plus-scenario discipline.

### Motivation

Doctor finding doctor-llm-objective-delta-uncovered-behavior (post-step of the lessons-brief-injection propose-change, 2026-07-04; path SPECIFICATION/contracts.md line 900, spec_root SPECIFICATION, severity medium), dispositioned propose-change by the maintainer: the since-version delta review (live vs v027) flagged that the changed region introduces an invariant stated without a BCP14 clause and with no scenario exercising it. The normative force of the sentence is unclear — it is ambiguous whether 'There is NO root research/ tree' binds future sessions and tooling (a placement rule the plan front-end and repo hygiene must honor) or merely describes the v028-era repository layout, and the spec is silent on where a standalone analysis artifact MUST land when no planning thread exists yet. The surrounding section states its other backstops (one handoff per topic; archived matches epic-closed) as enforced conformance concerns, so the descriptive register here is also inconsistent with its neighbors.

### Proposed Changes

**A. Normative restatement — `SPECIFICATION/contracts.md` §"The `plan/<topic>/` thread store".** The sentence "There is NO root `research/` tree: standalone analysis lives in a plan thread (or, once the thread closes, under `plan/archive/`), and a living reference document lives in `docs/`, `.ai/`, or a dedicated top-level topic directory (precedent: `loop-reflection-gate/`)." MUST be replaced with: "A root `research/` tree MUST NOT exist. Standalone analysis MUST live in a plan thread (or, once the thread closes, under `plan/archive/<topic>/`); a living reference document MUST live in `docs/`, `.ai/`, or a dedicated top-level topic directory (precedent: `loop-reflection-gate/`)."

**B. New scenario — `SPECIFICATION/scenarios.md`, appended as `## Scenario 42 — standalone analysis lands in a plan thread, not a root research tree`** (number provisional: the pending orchestrate-plan proposal claims 39 and the pending lessons-brief-injection proposal claims 40-41; renumber at revise as the queue lands):

```gherkin
Feature: analysis placement honors the retired research tree
  As a maintainer recording standalone analysis
  I want new analysis to land in the plan thread store
  So that no root research/ tree re-accretes after its fleet-wide retirement

Scenario: a new analysis note lands under the plan thread store
  Given a maintainer records standalone analysis for topic "t" via the plan front-end
  When the thread stores the reasoning note
  Then the note lands under plan/t/ (or plan/t/research/ for a sub-topic)
  And no root research/ path is created anywhere in the repository
```

**C. Heading-coverage co-edit — `tests/heading-coverage.json`.** The revise pass accepting this critique MUST add an entry for the new scenario `## ` heading via its `resulting_files[]` mechanism, per the repo's revise co-edit discipline (`test` MAY be the literal "TODO" with a non-empty reason naming the enforcing structural gate).
