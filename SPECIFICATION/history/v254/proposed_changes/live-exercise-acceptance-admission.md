---
topic: live-exercise-acceptance-admission
author: codex (repo-gates-and-test-integrity)
created_at: 2026-08-30T23:50:07Z
---

## Proposal: Central dispatch parks live-exercise acceptance

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require every central dispatch entry path to use one shared admission predicate that prevents live-exercise or live-verification acceptance criteria from entering an automatically closing acceptance path. The rule closes the measured gap in which the overseer seat rejects such an item while the autonomous central loop can admit the same item seconds later.

### Motivation

Plan repo-gates-and-test-integrity (source epic overseer-4z97, child overseer-4z97.6) measured that scripts/dispatch_acceptance_guard.py protects only the overseer seat-driven launch path. The central dispatcher in livespec-orchestrator-beads-fabro has no equivalent ratified admission rule, so an autonomous loop admitted the same live-exercise item seventeen seconds after the seat guard refused it. This obligation belongs to the central dispatcher rather than the overseer repository. Target plan live-exercise-acceptance-admission (epic bd-ib-ehso7x) owns ratification and the later execution mirror; the source item remains the cross-tenant provenance anchor until the implementation is verified and merged.

### Proposed Changes

Add a normative clause to `SPECIFICATION/contracts.md` defining live-exercise acceptance admission at the central dispatch boundary. Every direct, hand-picked, drained, and autonomous-loop dispatch entry path MUST reach one shared pre-claim predicate before an item is claimed or a run is created. When an item's effective acceptance criteria require a live exercise or live verification and its effective acceptance policy would otherwise permit automatic closure without a human acceptance leg, that predicate MUST refuse admission unless an explicit effective parking policy routes the item through `ai-then-human` or `human-only` acceptance. The refusal MUST identify the work item, state that a live-exercise criterion lacks an effective parking policy, and name the accepted remedy. The shared predicate MUST return the same verdict for the same item regardless of which dispatch entry path reached it, and implementations MUST NOT reproduce independent path-local versions of this decision.

The rule MUST remain narrow: an ordinary item whose criteria require no live exercise MUST remain admissible when its other admission conditions pass, and an item with a live-exercise criterion MUST remain admissible when an effective `ai-then-human` or `human-only` parking policy applies. The rule governs admission and acceptance routing; it MUST NOT prescribe the adopter-local text-matching implementation or move the overseer's unrelated acceptance-bar and dispatch-tier checks into the central dispatcher.

Add a scenario to `SPECIFICATION/scenarios.md` covering three observations against the same shared predicate: a live-exercise item under automatically closing acceptance is refused before claim from both a direct dispatch and the autonomous loop; an ordinary item is admitted; and a live-exercise item carrying an effective parking policy is admitted and remains parked for the required human leg. During revise, the ratification change MUST update `tests/heading-coverage.json` in the same commit so the new scenario heading is bound to the regression tests that exercise the central predicate.
