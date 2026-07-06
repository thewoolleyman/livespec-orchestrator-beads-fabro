---
topic: orchestrate-plan-surfaces-unarchived-plan-threads
author: claude-fable-5
created_at: 2026-07-04T05:38:04Z
spec_commitments:
  impl_followups:
    - id_hint: orchestrate-plan-thread-candidate-source
      description: |
        Extend plan_actions in .claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/orchestrate.py with the third composed candidate source: a read-only plan-thread scan over plan/*/ (excluding plan/archive/) emitting one human-gated plan:<topic> action per unarchived thread directory, plus run handling that returns status: human-gated with the /livespec-orchestrator-beads-fabro:plan <topic> handoff for a selected plan:<topic> action, degraded tolerance for a missing/empty plan/ directory, and tests covering the unarchived-visible / archived-invisible split per the new scenario.
---

## Proposal: orchestrate plan composes a third candidate source: unarchived plan threads

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the `orchestrate` operator surface's `plan` composition from two candidate sources (spec-side `/livespec:next`, impl-side `next`) to three, adding a read-only plan-thread scan of the `plan/` thread store that surfaces every unarchived planning thread as a human-gated, operator-selectable `plan:<topic>` action carrying a `/livespec-orchestrator-beads-fabro:plan <topic>` handoff. The scan is directory enumeration only (no ranking, no ledger reads); archived threads under `plan/archive/` never surface; a missing or empty `plan/` degrades to zero plan-thread actions without failing `plan`. `run` treats a selected `plan:<topic>` action exactly like a spec action: `status: human-gated` plus the handoff, no mutation. The Planning Lane restraint budget is clarified so the scan is counted as a composed candidate source inside the existing `orchestrate` surface, not a second front-end. A new scenario ratifies the unarchived-visible / archived-invisible split.

### Motivation

Today an open planning thread is invisible to the operator selection surface unless its anchoring epic happens to have ready ledger work: the impl-side `next` is contractually a pure ranker over the beads store (it never scans the filesystem and its only action type is `implement`), and `orchestrate plan` is contractually pinned to composing exactly the two `next` outputs. So a thread sitting in `plan/<topic>/` with an open epic and no ready children never appears in `actions[]`, and the operator must remember it exists. The composition machinery already generalizes to N candidate sources (each source is an independent candidates[] emitter with per-source failure degradation), so the natural home for the nudge is a third composed source in `orchestrate plan` — not the impl-side ranker (which would break its pure-function-of-ledger-state contract) and not the Conformance Pattern (an unarchived thread with an open epic is a legitimate state to surface, not an invariant violation; conformance owns only the archived-vs-epic-closed mismatch per contracts.md §'Archive on epic close'). Spec-first ordering: the current contract text enumerates exactly two composed sources, so implementing the scanner before amending the contract would create impl→spec drift that capture-spec-drift would flag. In-flight alignment (surveyed 2026-07-04): five stale remote spec/* branches sit 48-170 commits behind master (their revision content already landed or was superseded) and none touch the plan composition; the pending proposed change 'approval-is-the-pending-approval-to-ready-transition' amends only §'`orchestrate`' human-valve and autonomous-mode text — this proposal ALIGNS with it by scoping its amendments to the composition intro, the `plan`/`run` action paragraphs, and the Planning Lane restraint budget, none of which that proposal touches.

### Proposed Changes

**A. Third composed source — `SPECIFICATION/contracts.md` §"`orchestrate`" intro.** The sentences "It composes the existing spec-side `/livespec:next` output with this plugin's impl-side `next` output and emits a small `actions[]` plan. It MUST NOT duplicate ranking logic from either `next` surface." MUST be replaced with: "It composes three read-only candidate sources — the existing spec-side `/livespec:next` output, this plugin's impl-side `next` output, and a plan-thread scan of the `plan/` thread store — and emits a small `actions[]` plan. It MUST NOT duplicate ranking logic from either `next` surface; the plan-thread scan is directory enumeration only and MUST NOT rank, order beyond lexicographic topic order, or filter beyond the unarchived/archived split."

**B. Plan-thread action records — `SPECIFICATION/contracts.md` §"`orchestrate`", `plan` paragraph.** In "`plan` is read-only. It resolves the target repo explicitly, invokes the spec-side and impl-side `next` wrappers, and returns selectable action records.", the phrase "invokes the spec-side and impl-side `next` wrappers" MUST become "invokes the spec-side and impl-side `next` wrappers and scans the `plan/` thread store". After the sentence "Impl actions have ids shaped as `impl:<work-item-id>` and are marked `factory_safe: true`." the paragraph MUST gain: "Plan-thread actions have ids shaped as `plan:<topic>` — exactly one per unarchived thread directory (every direct child directory of `plan/` except `plan/archive/`), in lexicographic topic order — are marked `factory_safe: false`, and carry a `/livespec-orchestrator-beads-fabro:plan <topic>` handoff. The scan MUST be read-only, MUST NOT surface archived threads (`plan/archive/<topic>/`), and MUST NOT consult the ledger: whether a thread's anchoring epic state matches its archived/unarchived placement remains the Conformance Pattern's concern (§'Archive on epic close'), not `plan`'s. A missing or empty `plan/` directory MUST yield zero plan-thread actions and MUST NOT fail the `plan` invocation — the same per-source degraded tolerance the two `next` sources already have (a failed source degrades to zero candidates from that source and is reported in the plan payload's per-source diagnostics)."

**C. `run` handling — `SPECIFICATION/contracts.md` §"`orchestrate`", `run` paragraph.** After the sentence "A selected spec action returns `status: human-gated` plus the handoff command; it MUST NOT mutate spec-side state directly." the paragraph MUST gain: "A selected plan-thread action (`plan:<topic>`) likewise returns `status: human-gated` plus its `/livespec-orchestrator-beads-fabro:plan <topic>` handoff; it MUST NOT mutate the thread store or the ledger."

**D. Restraint-budget clarification — `SPECIFICATION/contracts.md` §"Planning Lane restraint budget".** The paragraph MUST gain the closing sentence: "The `orchestrate` plan-thread scan (§'`orchestrate`') is a composed candidate source inside the existing operator surface, not a second front-end, and does not count against this budget."

**E. New scenario — `SPECIFICATION/scenarios.md`.** A new `## Scenario 39 — orchestrate plan surfaces unarchived plan threads` MUST be appended:

```gherkin
Feature: orchestrate plan surfaces unarchived plan threads
  As an operator selecting cross-side work
  I want open planning threads to appear as selectable actions
  So that an unarchived thread is never invisible merely because its epic has no ready ledger work

Scenario: unarchived threads surface in lexicographic order; archived threads do not
  Given a governed repo whose plan/ thread store contains unarchived thread directories plan/beta-topic/ and plan/alpha-topic/
  And an archived thread directory plan/archive/old-topic/
  When the operator invokes orchestrate plan --repo <path> --json
  Then actions[] contains exactly two plan-thread actions, plan:alpha-topic before plan:beta-topic, each factory_safe false and carrying its /livespec-orchestrator-beads-fabro:plan <topic> handoff
  And no action references old-topic or the plan/archive/ path
  And the invocation mutates nothing

Scenario: selecting a plan-thread action returns a human handoff
  Given the actions[] above
  When the operator invokes orchestrate run --repo <path> --action plan:alpha-topic --json
  Then the result carries status: human-gated and the /livespec-orchestrator-beads-fabro:plan alpha-topic handoff
  And the thread store and the ledger are unchanged

Scenario: a repo with no plan directory yields zero plan-thread actions
  Given a governed repo with no plan/ directory
  When the operator invokes orchestrate plan --repo <path> --json
  Then actions[] contains no plan: actions
  And the invocation exits 0
```

**F. Heading-coverage co-edit.** The revision accepting this proposal MUST co-edit `tests/heading-coverage.json` atomically, appending an entry for the new `## Scenario 39 — orchestrate plan surfaces unarchived plan threads` heading (`spec_root: SPECIFICATION`, `spec_file: scenarios.md`, `test: TODO` until the declared impl follow-up binds a real integration-tier test node id), per the repo's heading-coverage discipline (`SPECIFICATION/constraints.md` closed-but-unproven prohibition; `SPECIFICATION/contracts.md` `closed_item_integrity`). This proposal intentionally does NOT amend the human-valve action paragraphs, Scenario 31, or the autonomous-mode text — those are owned by the concurrently pending proposed change `approval-is-the-pending-approval-to-ready-transition`, with which this proposal is alignment-checked.
