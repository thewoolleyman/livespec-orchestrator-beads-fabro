---
topic: pending-approval-to-ready-structural-gate-ownership
author: claude-fable-5
created_at: 2026-07-03T08:26:36Z
---

## Proposal: pending-approval → ready is the structural grooming gate; admission is the sole human approval act

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Resolve the ownerless `pending-approval → ready` transition for effective-`manual`-admission items by making the transition purely STRUCTURAL: a Definition-of-Ready-passing item transits `pending-approval` and proceeds to `ready` regardless of its effective `admission_policy`, and ALL human permission is exercised at the admission valve (`ready → active`), where the Dispatcher auto-admits effective-`auto` items and holds effective-`manual` items for the `approve:` valve action. The conditional routing parenthetical — "approved on into `ready` when its effective `admission_policy` is `auto`" — is removed from the two contracts.md routing statements and the two scenarios.md routing lines; Scenarios 23 and 31 are unchanged and become the sole approval semantics.

### Motivation

The ratified v020–v026 lifecycle leaves an effective-`manual`-admission item's `pending-approval → ready` transition with no owner: the capture routing clause advances only effective-`auto` items into `ready`; the `approve:` valve action (contracts.md §"`orchestrate`" → "Human valve actions") acts on items ALREADY at `ready`; and the Dispatcher's manual-admission hold (Scenario 23) likewise presumes the item reached `ready`. The v023 critique's approval-model finding was resolved toward valve-side admission ("the human's explicit admission IS the approval act"), but the conditional "approved on into `ready` when … `auto`" routing language survived, stranding manual-admission items at `pending-approval` with no named actor to progress them. Filed from the lifecycle-front-end-retrofit track (plan/lifecycle-front-end-retrofit/, epic bd-ib-ew7bdv; slice bd-ib-r3vsnd implements the capture-routing clause as ratified at implementation time), maintainer pre-approved via the overseer session 2026-07-03.

### Proposed Changes

The resolution: `pending-approval → ready` is the STRUCTURAL grooming gate only. A Definition-of-Ready-passing item MUST proceed through `pending-approval` into `ready` regardless of its effective `admission_policy`; the transit satisfies the ratified invariant that reaching `ready` requires transiting `pending-approval` (§"Work-item beads-issue mapping" invariants, which stay unchanged). `admission_policy` MUST govern only the admission valve (`ready → active`): the Dispatcher auto-admits effective-`auto` `ready` items and MUST hold effective-`manual` `ready` items for the operator's `approve:` valve action — the human's explicit admission IS the approval act (Scenarios 23 and 31, both unchanged).

Four ratified statements carry the superseded conditional language and MUST be amended:

1. `SPECIFICATION/contracts.md` §"The four maintainer touchpoints" item 1 ("Capture / intake (augmented)"): replace "a Definition-of-Ready-passing item lands in `pending-approval` (approved on into `ready` when its effective `admission_policy` is `auto`)" with "a Definition-of-Ready-passing item transits `pending-approval` and proceeds to `ready` regardless of its effective `admission_policy` — the transit is the structural grooming gate, not an approval hold; all human permission is exercised at the admission valve (`ready → active`), where the Dispatcher auto-admits effective-`auto` items and holds effective-`manual` items for the `approve:` valve action".

2. `SPECIFICATION/contracts.md` §"Gap-detectable behavior clauses", the capture-front-end routing clause: replace "… above-floor item lands in `pending-approval` (approved on into `ready` when its effective `admission_policy` is `auto`)" with "… above-floor item MUST transit `pending-approval` and proceed into `ready` regardless of its effective `admission_policy` (the structural grooming-gate transit; `admission_policy` governs only the `ready → active` admission valve)". The remainder of the clause (epic → `backlog`; not-autonomously-verifiable → `blocked` + `blocked_reason: needs-human`; unresolved blockers → linked edges, never directly `ready`) is unchanged.

3. `SPECIFICATION/scenarios.md`, the capture-impl-gaps flow line: replace "And the intake Definition-of-Ready routes it (a DoR-passing item lands `pending-approval`, approved into `ready` when its effective admission_policy is `auto`)" with "And the intake Definition-of-Ready routes it (an item that passes the Definition-of-Ready checklist transits `pending-approval` and proceeds to `ready`; admission policy is exercised at the admission valve, not by this routing)". (The quoted current text keeps its "DoR-passing" spelling only because a replacement target must match the file verbatim; the replacement text spells the term out — the "DoR" acronym is banned per maintainer direction, 2026-07-04, and this amendment removes its last live-spec occurrence at ratification.)

4. `SPECIFICATION/scenarios.md` §"Scenario 8 — Intake Definition-of-Ready triage", the single-acceptance-item scenario: replace "Then it lands in `pending-approval` and is approved into `ready` when its effective admission_policy is `auto`" with "Then it transits `pending-approval` and proceeds to `ready` regardless of its effective admission_policy", and replace the following "And it is eligible for autonomous dispatch" with "And it awaits the admission valve (auto-admitted when its effective admission_policy is `auto`; held for the `approve:` valve action when `manual`)".

One non-normative wording clarification rides along: `SPECIFICATION/contracts.md` §"Resolved realization choices", the `defer` bullet, SHOULD replace "(still groomed, just un-approved)" with "(still groomed, pulled from the admission pool pending a maintainer's structural re-clearance back to `ready`)" so the resting state's vocabulary no longer implies an approval hold. This is a wording alignment of an existing note, not a new behavior clause.

No `## ` (H2) heading is added, renamed, or removed by this proposal, so no `tests/heading-coverage.json` co-edit is required at revise time; the amended clause and scenarios already carry their existing coverage entries. Scenario 23 ("Dispatcher holds a manual-admission item until approved") and Scenario 31 ("orchestrate human valve actions") are intentionally NOT modified — they already express the valve-side approval model this proposal makes exclusive.
