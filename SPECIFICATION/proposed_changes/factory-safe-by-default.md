---
topic: factory-safe-by-default
author: claude-opus-4-8
created_at: 2026-07-17T21:07:29Z
---

## Proposal: First-class factory_safety opt-out axis (factory-safe by default)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/spec.md

### Summary

Add a first-class `factory_safety` work-item field — the machine-readable opt-out for the small enumerable residue of work that genuinely cannot run in an agent-written-code sandbox — encoded as a beads label prefix exactly like the existing policy fields. An absent label reads back `None`, meaning FACTORY-SAFE: the fleet is factory-safe BY DEFAULT, and only an explicit reason opts a work-item out. The field lives on the shared `livespec_runtime.work_items.types.WorkItem`, so both orchestrator substrates carry it.

### Motivation

Today the not-factory-safe classification is implicit and prose-buried: the shipped Dispatcher recognises a host-only item by a regex over the item's title/description (`is_host_only_item`), which nothing validates, nothing can filter on, and which is only discovered deep in a dispatch. Promoting it to a first-class field with a fixed reason enum makes the opt-out explicit, mechanically checkable, and enforceable fail-fast at admission (see the companion proposals). Motivated by the 2026-07-07 dispatch wave (design of record: repo `thewoolleyman/livespec`, `plan/factory-safe-by-default/research/design.md` §"Reshape (2026-07-17)").

### Proposed Changes

**(1) Extend the label-encoding list in §"Work-item beads-issue mapping".**

REPLACE (verbatim — the `blocked_reason` bullet):

```
- `admission_policy` — beads label `admission:<auto|manual>`;
  `acceptance_policy` — beads label `acceptance:<ai-only|human-only|ai-then-human>`;
  `blocked_reason` — beads label `blocked-reason:<needs-human|infra-external>`
  (the STORED reasons only; the third reason `dependency` is DERIVED and
  NEVER stored — it surfaces only as a rendered lane reason). An absent
  policy/reason label reads back `None` (inherit / the system safe
  default — the blessed optional-on-read pattern).
```

WITH (append a new `factory_safety` bullet immediately after it):

```
- `admission_policy` — beads label `admission:<auto|manual>`;
  `acceptance_policy` — beads label `acceptance:<ai-only|human-only|ai-then-human>`;
  `blocked_reason` — beads label `blocked-reason:<needs-human|infra-external>`
  (the STORED reasons only; the third reason `dependency` is DERIVED and
  NEVER stored — it surfaces only as a rendered lane reason). An absent
  policy/reason label reads back `None` (inherit / the system safe
  default — the blessed optional-on-read pattern).
- `factory_safety` — beads label
  `factory-safety:<needs-host-secrets|mutates-host-machinery|needs-privileged-host>`.
  An absent label reads back `None`, meaning FACTORY-SAFE — the fleet is
  factory-safe BY DEFAULT and only an explicit reason opts out. The three
  reasons name work that genuinely cannot run in a sandbox executing
  agent-written code: `needs-host-secrets` (verification requires real
  secrets that must never enter such a sandbox), `mutates-host-machinery`
  (changes the live host substrate the factory itself runs on — systemd
  timers, credential wrappers, the plugin cache, Fabro servers), and
  `needs-privileged-host` (privileged provisioning — a Dolt server, a
  1Password environment, a per-tenant Fabro server). The sharp line:
  writing CODE for any of these (including the Dispatcher's own code) is
  factory-safe; APPLYING host state is host-only.
```

**(2) Add `factory_safety` to the logical field-set enumeration** in the same section's preamble.

REPLACE (verbatim):

```
`livespec_runtime.work_items.types.WorkItem` (the 7-state `status`,
required non-null `rank`, the `admission_policy`/`acceptance_policy`/
`blocked_reason` policy fields, reused `assignee`; `priority` dropped);
```

WITH:

```
`livespec_runtime.work_items.types.WorkItem` (the 7-state `status`,
required non-null `rank`, the `admission_policy`/`acceptance_policy`/
`blocked_reason` policy fields, the `factory_safety` runnability field,
reused `assignee`; `priority` dropped);
```

Because the field is added to the SHARED `livespec_runtime` `WorkItem`, this is a cross-repo change: the plaintext-sibling orchestrator (`livespec-orchestrator-git-jsonl`) shares the same dataclass and MUST carry the field for parity (its closed-key store codec must admit or pop it, exactly as it already does for `admission_policy`/`acceptance_policy`/`blocked_reason`).

**(3) Distinguish `factory_safety` from `blocked_reason: infra-external`** so the two do not overlap ambiguously. In §"Work-item state semantics", where `blocked` is defined, add a clarifying sentence. The two are different axes: `blocked_reason: infra-external` is a TRANSIENT lifecycle STATE — the item is in `blocked` because something outside the factory is *currently* preventing progress, and it clears when that external thing resolves. `factory_safety` is an INTRINSIC, capture-time classification of the work ITSELF — the work is permanently host-only regardless of external state; a factory-safe-opted-out item is `ready`/dispatchable-in-principle but MUST be routed to a host actor rather than an agent sandbox, and it never "clears."

**(4) Drift-completeness (spec.md glossary).** In `spec.md`'s "Beads issue (work-item)" glossary entry, add `factory-safety:` to the label enumeration that currently reads "the `admission:` / `acceptance:` / `blocked-reason:` policies" so the glossary label set stays complete.

## Proposal: Two orthogonal axes: correct the admission_policy / host-only conflation

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Correct two clauses that wrongly claim `admission_policy` "replaces the prior host-only marker." `admission_policy` gates PERMISSION (does a human approve? — the `pending-approval → ready` routing); it structurally cannot express RUNNABILITY (can an agent sandbox run this work at all? — the `ready → active` valve). The host-only marker's runnability role is now the separate `factory_safety` axis. Only the `human-gated` lineage is realized by `admission_policy`.

### Motivation

The shipped Dispatcher already refuses host-only items at the `ready → active` boundary via a title/description regex — direct evidence that `admission_policy` did NOT absorb the host-only role, and that the spec's "replaces" claim is contradicted by the code. A human approving a host-only item under `admission_policy: manual` merely sends it into a sandbox that physically cannot run it. Permission and runnability are orthogonal.

### Proposed Changes

**(a) §"Admission valve (`ready → active`)" — the primary correction.**

REPLACE (verbatim):

```
  `admission_policy` field is the first-class realization that
  **replaces the prior `host-only` / `human-gated` text markers** —
  risky / irreversible work is held at the `approve` gate (resting at
  `pending-approval`), never by a pre-merge acceptance gate. The
```

WITH:

```
  `admission_policy` field is the first-class realization that
  **replaces the prior `human-gated` text marker** — risky / irreversible
  work is held at the `approve` gate (resting at `pending-approval`), never
  by a pre-merge acceptance gate. It does NOT carry the prior `host-only`
  marker's role: `admission_policy` gates PERMISSION (does a human
  approve?), which is ORTHOGONAL to RUNNABILITY (can an agent sandbox run
  this work at all?). Runnability is the separate `factory_safety` axis
  (§"Work-item beads-issue mapping"), enforced at this same valve (below).
  The
```

(The trailing bare `The` is preserved so the following sentence — "The Dispatcher MUST NOT hold an item at `ready` awaiting a human …" — reads unchanged.)

**(b) §"Dispatcher grooming behavior" — the lineage parenthetical.**

REPLACE (verbatim, the parenthetical fragment):

```
(the first-class realization of the risky/irreversible human gate — the prior `host-only` / `human-gated` lineage; a spec-change decision
```

WITH:

```
(the first-class realization of the risky/irreversible human gate — the prior `human-gated` lineage (the orthogonal `host-only` runnability marker is now the `factory_safety` axis, not this field); a spec-change decision
```

Do NOT touch the adjacent, already-correct `human-gated → admission_policy` mapping later in §"Dispatcher grooming behavior" (the "the prior `human-gated` marker is realized by the item's effective `admission_policy == manual`" sentence) — it mentions only `human-gated` and is consistent.

## Proposal: Dispatcher refuses a not-factory-safe item at the ready-to-active valve (fail-fast, host-route)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Make factory-safety a dispatch-admission condition. At the `ready → active` valve the Dispatcher MUST refuse an item whose `factory_safety` is non-null BEFORE launching any sandbox run, and MUST surface it for host routing rather than dispatching it and failing deep in the sandbox — turning a ~19-minute sandbox burn into an instant, actionable refusal. Every enumeration of the admission-eligibility set is amended to include factory-safety, an explicit `--item` target is refused identically, and a Gherkin scenario is added.

### Motivation

This is the fail-fast half of factory-safe-by-default: the system classifies and refuses mechanically, replacing fuzzy per-item human judgment. It aligns the spec with the already-shipped pre-launch refusal while moving the decision to the admission valve so a not-factory-safe item is never selected for a sandbox in the first place.

### Proposed Changes

**(a) §"Admission valve (`ready → active`)" — add factory-safety to the eligibility set and state the refusal behavior.**

REPLACE (verbatim, the lead-in):

```
So the valve's remaining conditions are
purely mechanical — capacity, dependencies, and a resolvable assignee:
```

WITH:

```
So the valve's remaining conditions are
mechanical — capacity, dependencies, a resolvable assignee, and factory-safety:
```

ADD a new bullet immediately after the `**Assignee resolvable:**` bullet:

```
- **Factory-safe:** an item whose `factory_safety` is non-null names work
  that cannot run in an agent sandbox. The Dispatcher MUST refuse to admit
  it — BEFORE launching any sandbox run — and MUST surface an actionable
  host-route refusal naming the reason, rather than dispatching it and
  failing deep in the sandbox. The item is NOT marked `blocked` (its
  runnability is intrinsic, not a transient external block); it is surfaced
  for host routing via the needs-attention awareness surface for a host
  actor to run. The Dispatcher MUST NOT retry it into a sandbox.
```

REPLACE (verbatim, the eligibility recap):

```
admission-eligible `ready` item (eligible = dependencies clear
AND an assignee is resolvable — `admission_policy` plays no part at this
valve)
```

WITH:

```
admission-eligible `ready` item (eligible = dependencies clear
AND an assignee is resolvable AND `factory_safety` is null —
`admission_policy` plays no part at this valve)
```

**(b) §"Work-item state semantics" — the second valve enumeration.**

REPLACE (verbatim):

```
The admission valve (`ready →
active`) is purely mechanical — dependencies clear, a free WIP slot,
an assignee resolvable; permission was settled upstream at `approve`.
```

WITH:

```
The admission valve (`ready →
active`) is mechanical — dependencies clear, a free WIP slot,
an assignee resolvable, and `factory_safety` null (a non-null value is
refused at admission and host-routed); permission was settled upstream at
`approve`.
```

**(c) §"Dispatcher loop invocation surface" — `--item` narrows-never-bypasses.**

REPLACE (verbatim, the eligibility parenthetical):

```
a named item that is not dispatch-eligible (dependencies unclear, no
  resolvable assignee, no free WIP slot, or resting at `pending-approval`
  under an effective `admission_policy` of `manual`) MUST NOT be dispatched,
```

WITH:

```
a named item that is not dispatch-eligible (dependencies unclear, no
  resolvable assignee, no free WIP slot, resting at `pending-approval`
  under an effective `admission_policy` of `manual`, or carrying a non-null
  `factory_safety`) MUST NOT be dispatched,
```

This makes an explicitly `--item`-targeted not-factory-safe item refused identically to an unnamed one — the explicit target narrows, it never bypasses.

**(d) §"Work-item beads-issue mapping" invariants block — the doctor-checkable recap.**

REPLACE (verbatim):

```
the admission valve
> checks only capacity, dependencies, and assignee; every live
```

WITH:

```
the admission valve
> checks capacity, dependencies, assignee, and factory-safety; every live
```

NOTE (for the revise + impl slice): this recap is doctor-ENFORCED prose. The paired doctor invariant that asserts the admission-valve check set MUST be updated in lockstep with the impl slice so the contract and the check do not drift.

**(e) scenarios.md — new Gherkin scenario (behavior ⇒ scenario discipline).**

ADD a new `## Scenario NN — Dispatcher refuses a not-factory-safe item at admission` (NN = the next free scenario number), modeled on the existing dispatch-refusal scenarios (Scenario 19, credential-freshness refusal; Scenario 30, baseline-conformance abort):

```
## Scenario NN — Dispatcher refuses a not-factory-safe item at admission

Feature: A ready work-item whose `factory_safety` is non-null is refused at
  the admission valve before any sandbox launch and surfaced for host routing.

  Scenario: A ready item carrying factory_safety needs-host-secrets is refused
    Given a `ready` work-item whose `factory_safety` is `needs-host-secrets`
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is not admitted to `active`
    And no Fabro sandbox run is launched for it
    And the Dispatcher surfaces an actionable host-route refusal naming the
      `needs-host-secrets` reason
    And the item stays `ready` (it is not marked `blocked`)
```

**(f) `tests/heading-coverage.json` co-edit (REQUIRED by the new H2).** The new `## Scenario NN` is a new H2 heading, so the same revise payload MUST add a matching `TODO`+`reason` entry to `tests/heading-coverage.json` (path spelled `../tests/heading-coverage.json` when `--spec-target` is the main `SPECIFICATION/` tree), per the revise co-edit discipline. No other edit in this proposal changes an H2, so no other heading-coverage change is needed.

**(g) Additional eligibility drift sites (surfaced by independent review).** Two more enumerations assert the three admission conditions are SUFFICIENT and must gain the factory-safety condition too.

REPLACE (verbatim — §"The skill surface", the `approve:` action-id description in contracts.md):

```
admission to
`active` then follows mechanically when a WIP slot frees, dependencies
are clear, and an assignee resolves
```

WITH:

```
admission to
`active` then follows mechanically when a WIP slot frees, dependencies
are clear, an assignee resolves, and `factory_safety` is null
```

REPLACE (verbatim — scenarios.md, Scenario 31's approve Gherkin):

```
  And admission to `active` then follows mechanically when a WIP slot frees, dependencies are clear, and an assignee resolves
```

WITH:

```
  And admission to `active` then follows mechanically when a WIP slot frees, dependencies are clear, an assignee resolves, and `factory_safety` is null
```

Both edits are inside existing H2 headings, so neither needs a `tests/heading-coverage.json` co-edit.
