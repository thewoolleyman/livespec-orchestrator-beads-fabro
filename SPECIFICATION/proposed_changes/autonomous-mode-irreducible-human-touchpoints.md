---
topic: autonomous-mode-irreducible-human-touchpoints
author: claude-opus-4-8
created_at: 2026-07-10T00:00:00Z
---

## Proposal: Name the irreducible human touchpoints as truly-unresolvable by design

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

The v032 Full-autonomous-mode spec defines "truly-unresolvable" only as a
CONFIDENCE test (the LLM cannot resolve it with sufficient confidence, it needs
unobtainable information, or a policy marks it human-only). It never names the
decisions that must stay human even when the engine is fully confident, and in
one place says the opposite: the admission collapse "auto-approving even items
whose stored `admission_policy` is `manual`" would auto-admit a spec-change
slice, because §"Grooming and slice-size calibration" makes `admission_policy:
manual` "the first-class realization of the prior `human-gated` spec-change
marker." This proposal names the three design-human-gated decisions — drift
acceptance, spec-change slices, and the regroom / backlog bounce — as
truly-unresolvable BY DESIGN (not by low confidence), splits the collapse's
routine-`manual` auto-approval from the design-gated `manual` tier so a
spec-change slice is never auto-admitted, and reconciles the blanket "treat
every item's effective `acceptance_policy` as `ai-only`" with Scenario 36's
`human-only` carve-out. It also closes two residual `manual` ↔ spec-change
conflations that survive elsewhere in `contracts.md` (§"Dispatcher grooming
behavior" and §"The four maintainer touchpoints") and adds a `scenarios.md`
Scenario-36 case for a design-human-gated decision escalating by design even at
high LLM confidence. It changes no `## ` (H2) heading, so no
`tests/heading-coverage.json` co-edit is required.

### Motivation

This is deliverable (1) of orchestrator plan step O1
(`livespec-orchestrator-beads-fabro/plan/autonomous-mode/design.md` §3; the
overall plan `livespec/plan/autonomous-mode/design.md` §4). The autonomous-mode
engine (tracked by the existing unbuilt item `bd-ib-82a`, the O2 build) MUST
leave the irreducible human touchpoints escalated. Step 0 (the independent Fable
validation, 2026-07-10, NO-BLOCKERS) verified the v032 spec does NOT protect
these decisions and in one place would collapse one of them.

Attribution, stated exactly as the design record requires (overall plan §4):
only **drift acceptance** is normative livespec-core law — core `spec.md`
§"Contract + reference implementations architecture" calls it "the irreducible
human touchpoint that survives even a fully autonomous orchestrator. Orchestrators
MAY file drift (the machine path); only humans accept it." **Spec-change gating**
and **regroom-stays-human** are core NON-normative grooming guidance (core
`non-functional-requirements.md`, which core marks explicitly non-normative on
its contract), promoted to a hard boundary for THIS plugin by maintainer
declaration (2026-07-10). They are cited as such below, never as existing core
contract.

The regroom / backlog bounce is structurally safe today (a bounce lands in
`backlog`, which is outside the `pending-approval → ready` collapse's reach), so
this proposal codifies the invariant without adding machinery for it. The
residual exposures the collapse text actually creates are (a) a spec-change slice
carrying `manual` admission and (b) an explicit `human-only` acceptance policy;
both are closed here. The impl follow-up is the existing O2 engine item
`bd-ib-82a` — this proposal files no new work-item.

### Proposed Changes

All target text below is quoted verbatim from the live spec at
`origin/master` (v032, release 0.13.12). Twelve edits across four files; no `## `
(H2) heading is added, changed, or removed. This proposal is DISJOINT from its
sibling `autonomous-mode-arming-and-audit-contract`: where both touch `spec.md`
§"Full autonomous mode", `contracts.md` §"Full autonomous mode", and
`scenarios.md` they target different, non-overlapping verbatim strings (this
proposal's Scenario 36 vs the sibling's Scenarios 33/37), so the two may be
revised in either order.

**A. `SPECIFICATION/spec.md` §"Terminology" — refine the truly-unresolvable
definition and name the design-gated set.** Replace the verbatim block:

> **Truly-unresolvable decision** — Under §"Full autonomous mode", a
> human-delegable decision the autonomous engine MUST NOT auto-resolve
> because the LLM cannot resolve it with sufficient confidence, it requires
> information the engine cannot obtain, or a policy marks it human-only.
> Truly-unresolvable decisions are the residual escalation class that even
> full autonomous mode still surfaces to a human — the sole exception to the mode's otherwise-total collapse of the human-delegable gates.

with:

> **Truly-unresolvable decision** — Under §"Full autonomous mode", a
> human-delegable decision the autonomous engine MUST NOT auto-resolve —
> either because it is human-gated BY DESIGN (the design-human-gated set
> below) or because the LLM cannot resolve it with sufficient confidence, it
> requires information the engine cannot obtain, or a policy marks it
> human-only. Truly-unresolvable decisions are the residual escalation class
> that even full autonomous mode still surfaces to a human — the sole
> exception to the mode's otherwise-total collapse of the human-delegable
> gates.
>
> The set has TWO disjoint sources. The first is CONFIDENCE-bounded: a
> decision the LLM cannot confidently resolve, or one needing information the
> engine cannot obtain. The second is DESIGN-bounded — three decisions that
> stay human even when the engine is fully confident, because a human, not the
> engine, owns them:
>
> - **Drift acceptance** — the engine MAY file impl→spec drift (the machine
>   path), but only a human accepts it. This is normative livespec-core law
>   (`livespec/SPECIFICATION/spec.md` §"Contract + reference implementations
>   architecture": "the irreducible human touchpoint that survives even a
>   fully autonomous orchestrator").
> - **Spec-change slices** — a slice whose autonomy tier is spec-change is
>   human-gated: it routes through `/livespec:propose-change` /
>   `/livespec:revise` and is never factory-dispatched or auto-admitted.
> - **Regroom / backlog bounce** — grooming stays human; a non-convergence
>   bounce lands in `backlog` and escalates, and is never auto-groomed.
>
> The latter two are core NON-normative grooming guidance
> (`livespec/SPECIFICATION/non-functional-requirements.md`, which core marks
> explicitly non-normative on its contract) promoted to a hard boundary for
> THIS plugin by maintainer declaration (2026-07-10); they are cited as such,
> not as existing core contract. All three are truly-unresolvable BY DESIGN,
> not by low confidence: full autonomous mode MUST leave them escalated as
> needs-attention and MUST NOT auto-resolve them.

**B. `SPECIFICATION/spec.md` §"Full autonomous mode" — add the design-gated
admission carve-out and the `human-only` acceptance carve-out to the collapse
bullet.** Replace the verbatim bullet:

> - treats every item's effective `admission_policy` as `auto`
>   (auto-approving `pending-approval` items into `ready` — collapsing the
>   `approve` gate) and every item's effective `acceptance_policy` as
>   `ai-only` (collapsing the human leg of `contracts.md` §"Post-merge
>   acceptance (`acceptance → done`)"); the admission valve (`ready →
>   active`) stays mechanical and unchanged;

with:

> - treats every ROUTINE item's effective `admission_policy` as `auto`
>   (auto-approving `pending-approval` items into `ready` — collapsing the
>   `approve` gate), EXCEPT a design-human-gated item (a spec-change-tier
>   slice; see §"Terminology"), which the mode MUST NOT auto-approve and MUST
>   leave escalated; and treats every item's effective `acceptance_policy` as
>   `ai-only` (collapsing the human leg of `ai-then-human` per `contracts.md`
>   §"Post-merge acceptance (`acceptance → done`)"), EXCEPT an item whose
>   effective `acceptance_policy` is `human-only`, a deliberate human gate
>   that stays truly-unresolvable and MUST still park; the admission valve
>   (`ready → active`) stays mechanical and unchanged;

**C. `SPECIFICATION/spec.md` §"Full autonomous mode" — broaden the guardrail
paragraph to include the design-gated set.** Replace the verbatim paragraph:

> The one thing full autonomous mode MUST NOT do is auto-resolve a
> **truly-unresolvable decision** (see §"Terminology"): a decision the LLM
> cannot confidently resolve MUST still be escalated and surfaced to a
> human, never guessed. Full autonomous mode changes WHO makes each routine
> decision; it does not remove the residual human escalation path, and it
> MUST NOT weaken the "no release with zero verification" floor — every
> acceptance still carries at least one AI pass.

with:

> The one thing full autonomous mode MUST NOT do is auto-resolve a
> **truly-unresolvable decision** (see §"Terminology"): a decision the LLM
> cannot confidently resolve — OR a decision that is human-gated by design
> (drift acceptance, a spec-change slice, or a regroom / backlog bounce) —
> MUST still be escalated and surfaced to a human, never guessed. Full
> autonomous mode changes WHO makes each routine decision; it does not remove
> the residual human escalation path, and it MUST NOT weaken the "no release
> with zero verification" floor — every acceptance still carries at least one
> AI pass.

**D. `SPECIFICATION/contracts.md` §"Autonomous-mode semantics" — split routine
`manual` from the design-gated tier in the admission-collapse bullet.** Replace
the verbatim bullet:

> - treat every item's effective `admission_policy` as `auto` —
>   auto-approving (`pending-approval → ready`) even items whose stored
>   `admission_policy` is `manual`, so no item rests at `pending-approval`
>   for a human (overriding, for this run only, the "MUST surface the
>   resting item for the maintainer's explicit `approve`" rule of
>   §"Admission valve (`ready → active`)"); admission to `active` then
>   follows the unchanged mechanical valve;

with:

> - treat every ROUTINE item's effective `admission_policy` as `auto` —
>   auto-approving (`pending-approval → ready`) even items whose stored
>   `admission_policy` is `manual` for reasons of routine risk or
>   irreversibility, so no such item rests at `pending-approval` for a human
>   (overriding, for this run only, the "MUST surface the resting item for
>   the maintainer's explicit `approve`" rule of §"Admission valve (`ready →
>   active`)"); admission to `active` then follows the unchanged mechanical
>   valve. This collapse MUST NOT auto-approve a DESIGN-HUMAN-GATED item — a
>   spec-change-tier slice (`spec.md` §"Terminology") — which is
>   truly-unresolvable by design and MUST stay escalated. Spec-change slices
>   route to `/livespec:propose-change` / `/livespec:revise` and are never
>   factory-dispatched (§"Grooming and slice-size calibration"), so the
>   collapse structurally cannot reach a well-routed slice; as a backstop the
>   engine MUST distinguish the design-human-gated tier from routine `manual`
>   admission by the spec-change autonomy tier of §"Grooming and slice-size
>   calibration", not by the `manual` value alone;

**E. `SPECIFICATION/contracts.md` §"Autonomous-mode semantics" — add the
`human-only` carve-out to the acceptance-collapse bullet.** Replace the verbatim
bullet:

> - treat every item's effective `acceptance_policy` as `ai-only` —
>   confirming acceptance from the AI pass without parking the item for the
>   human leg of `ai-then-human` (§"Post-merge acceptance (`acceptance →
>   done`)"), while still honoring "There MUST be no 'release with zero
>   verification' — every acceptance carries at least one AI pass"; and

with:

> - treat every item's effective `acceptance_policy` as `ai-only` —
>   confirming acceptance from the AI pass without parking the item for the
>   human leg of `ai-then-human` (§"Post-merge acceptance (`acceptance →
>   done`)"), while still honoring "There MUST be no 'release with zero
>   verification' — every acceptance carries at least one AI pass" — EXCEPT an
>   item whose effective `acceptance_policy` is `human-only`: that is a
>   deliberate human gate, truly-unresolvable by design, which the mode MUST
>   NOT collapse and which MUST still park for the human `accept` leg
>   (Scenario 36); and

**F. `SPECIFICATION/contracts.md` §"Autonomous-mode semantics" — name the
design-gated set in the truly-unresolvable exception paragraph.** Replace the
verbatim paragraph:

> The one exception is a **truly-unresolvable decision** (`spec.md`
> §"Terminology"): the engine MUST NOT auto-resolve a decision the LLM
> cannot confidently resolve; it MUST still escalate and surface it, exactly
> as it would outside autonomous mode (`blocked_reason: needs-human`,
> escalate-don't-drop). Full autonomous mode MUST NOT create net-new
> work-items outside the normal filing paths.

with:

> The one exception is a **truly-unresolvable decision** (`spec.md`
> §"Terminology"): the engine MUST NOT auto-resolve a decision the LLM cannot
> confidently resolve, NOR a decision that is human-gated by design — drift
> acceptance, a spec-change slice, or a regroom / backlog bounce; it MUST
> still escalate and surface every such decision, exactly as it would outside
> autonomous mode (`blocked_reason: needs-human`, escalate-don't-drop). Full
> autonomous mode MUST NOT create net-new work-items outside the normal
> filing paths.

**G. `SPECIFICATION/contracts.md` §"Autonomous-mode gap-detectable clauses" —
qualify the auto-approve clause.** Replace the verbatim clause:

> - Under full autonomous mode the Dispatcher MUST auto-approve a `pending-approval` `manual`-admission item into `ready` without a human approval; admission to `active` then follows the unchanged mechanical valve.

with:

> - Under full autonomous mode the Dispatcher MUST auto-approve a `pending-approval` ROUTINE `manual`-admission item (held for routine risk or irreversibility) into `ready` without a human approval; admission to `active` then follows the unchanged mechanical valve. The Dispatcher MUST NOT auto-approve a design-human-gated item — a spec-change-tier slice — which stays escalated as truly-unresolvable; it distinguishes the design-human-gated tier from routine `manual` admission by the spec-change autonomy tier of §"Grooming and slice-size calibration", not by the `manual` value alone.

**H. `SPECIFICATION/contracts.md` §"Autonomous-mode gap-detectable clauses" —
enumerate the design-gated set in the still-escalate clause.** Replace the
verbatim clause:

> - Under full autonomous mode the Dispatcher MUST still escalate every
>   truly-unresolvable decision and MUST NOT auto-resolve it.

with:

> - Under full autonomous mode the Dispatcher MUST still escalate every
>   truly-unresolvable decision — including the three human-gated-by-design
>   decisions (drift acceptance, a spec-change slice, and a regroom / backlog
>   bounce) and any `human-only` acceptance — and MUST NOT auto-resolve it.

**I. `SPECIFICATION/constraints.md` §"Full autonomous mode constraints" — name
the design-gated set in the "Still escalate the unresolvable" rail.** Replace the
verbatim bullet:

> - **Still escalate the unresolvable.** The mode MUST NOT auto-resolve a
>   decision the LLM cannot confidently resolve; a truly-unresolvable
>   decision MUST still block and surface to a human. The "no release with
>   zero verification" floor of `contracts.md` §"Post-merge acceptance
>   (`acceptance → done`)" MUST hold — every acceptance carries at least one
>   AI pass even under the mode.

with:

> - **Still escalate the unresolvable.** The mode MUST NOT auto-resolve a
>   decision the LLM cannot confidently resolve, NOR a decision that is
>   human-gated by design — drift acceptance, a spec-change slice, or a
>   regroom / backlog bounce (`contracts.md` §"Full autonomous mode",
>   `spec.md` §"Terminology"); every such truly-unresolvable decision MUST
>   still block and surface to a human. The "no release with zero
>   verification" floor of `contracts.md` §"Post-merge acceptance
>   (`acceptance → done`)" MUST hold — every acceptance carries at least one
>   AI pass even under the mode.

**J. `SPECIFICATION/contracts.md` §"Dispatcher grooming behavior" — fix the
residual `manual` ↔ spec-change conflation parenthetical.** Replace the verbatim
sentence:

> The Dispatcher MUST NOT auto-approve (`pending-approval → ready`) any item whose effective `admission_policy` is `manual` (the first-class realization of the prior `human-gated` spec-change marker) — it surfaces the resting item for the maintainer's explicit `approve` instead of advancing it (the authoritative gate + valve contract is §"Dispatcher admission, WIP cap, and post-merge acceptance").

with:

> The Dispatcher MUST NOT auto-approve (`pending-approval → ready`) any item whose effective `admission_policy` is `manual` (the first-class realization of the risky/irreversible human gate — the prior `host-only` / `human-gated` lineage; a spec-change decision is human-gated by ROUTING to `/livespec:propose-change` rather than by resting here, per the intake autonomy-tier rule "spec-change is human-gated … and routes to `/livespec:propose-change` / `/livespec:revise`") — it surfaces the resting item for the maintainer's explicit `approve` instead of advancing it (the authoritative gate + valve contract is §"Dispatcher admission, WIP cap, and post-merge acceptance").

**K. `SPECIFICATION/contracts.md` §"The four maintainer touchpoints" — fix the
"spec-change / risky tier" conflation in the Dispatch touchpoint.** Replace the
verbatim fragment:

> (effective `admission_policy` `manual`, the spec-change / risky tier)

with:

> (effective `admission_policy` `manual`, the risky/irreversible tier — a spec-change decision is human-gated by routing to `/livespec:propose-change`, not by resting here)

**L. `SPECIFICATION/scenarios.md` Scenario 36 — add a second Gherkin scenario
for a design-human-gated decision escalating by design.** Replace the verbatim
block:

> Scenario: A truly-unresolvable decision escalates even under autonomous mode
>   Given full autonomous mode is enabled for the invocation
>   And a decision the LLM cannot confidently resolve, or which policy marks human-only
>   When the engine evaluates it
>   Then it does not auto-resolve the decision
>   And the item remains blocked with blocked_reason needs-human and is surfaced to a human
>   And the escalation is queryable from the journal

with:

> Scenario: A truly-unresolvable decision escalates even under autonomous mode
>   Given full autonomous mode is enabled for the invocation
>   And a decision the LLM cannot confidently resolve, or which policy marks human-only
>   When the engine evaluates it
>   Then it does not auto-resolve the decision
>   And the item remains blocked with blocked_reason needs-human and is surfaced to a human
>   And the escalation is queryable from the journal
>
> Scenario: A design-human-gated decision escalates by design even at high confidence
>   Given full autonomous mode is enabled for the invocation
>   And a design-human-gated decision — a drift acceptance, a spec-change, or a regroom/backlog-bounce — that the LLM could resolve with high confidence
>   When the engine evaluates it
>   Then it does not auto-resolve the decision because the design reserves it to a human
>   And the decision is left on its human path — a spec-change to `/livespec:propose-change`, a drift acceptance to the Spec-Plane revise path, a bounce resting in backlog — and surfaced to a human
>   And the escalation is queryable from the journal
