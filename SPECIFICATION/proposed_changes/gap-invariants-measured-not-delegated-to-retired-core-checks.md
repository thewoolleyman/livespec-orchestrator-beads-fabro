---
topic: gap-invariants-measured-not-delegated-to-retired-core-checks
author: claude-opus-5-5
created_at: 2026-10-24T03:33:51Z
---

## Proposal: State the gap invariants as the behaviour this plugin guarantees, not as livespec core doctor checks that core retired

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Four places in this repository's specification make livespec core's doctor checks `gap-tracking-one-to-one` and `no-stale-gap-tied` the verification bar, or name core's doctor as a consumer of `detect-impl-gaps` and `list-work-items`. Core retired those checks, and every other work-item invariant, from its shipped doctor on 2026-06-10, so no build of core can run them. This proposal restates the bar as the two behaviours the checks verified. No gap id is carried by more than one live gap-tied work-item. Every live gap-tied work-item carries a gap id that `detect-impl-gaps --json` emits. It also removes the consumer bullet and the two handoff entries that name core's doctor.

### Motivation

livespec core retired its work-item doctor invariants in spec v103 (core commit 01c8324b, 2026-06-10, "accept contract + reference implementations Phase 1"). Its `tests/livespec/doctor/static/test___init__.py` pins their absence: it lists `doctor-no-stale-gap-tied`, `doctor-no-duplicate-gap-id`, `doctor-no-orphan-dependency`, `doctor-no-stalled-epic`, `doctor-depends_on-ref-wellformedness` and `doctor-unresolved-spec-commitment` as checks that MUST NOT be registered. Its live `constraints.md` names `config-named-cli-callability` as the single cross-boundary invariant. The current core build (a71ff4c9f267) ran its static doctor on this repository on 2026-10-24 and passed every check it has; none of them is a gap check. This repository's clause "Migration of clause-derived gap ids" nevertheless says its implementation MUST NOT be reported complete until "livespec core's `gap-tracking-one-to-one` and `no-stale-gap-tied` invariants pass on this repository". The scenario "Clause-derived gap ids are migrated to heading-derived ones" repeats that as a Then step. Read literally, both demand a report no doctor can produce, so the clause can never be discharged, and any work-item that copies the wording into its Definition of Done becomes unsatisfiable. The migration work-item bd-ib-5t3zzv did exactly that. On 2026-10-24 the migration ran on the host: the one live gap-tied item, bd-ib-c3txja, was re-labelled from gap-cfurctzv to gap-lsyne5kg, and the 24 closed gap-tied items kept their historical labels. Both behaviours were then measured directly over all 1,610 items against the 149 ids the detector emitted. No gap id was carried twice, and no live item carried an id the detector does not emit. As a positive control, the pre-migration id gap-cfurctzv is not emitted, so the stale check would have fired before the migration. The same retirement makes the detect-impl-gaps consumer bullet and the Cross-boundary handoffs entries 2 and 3 describe calls that no longer happen. The generalization target is the existing paragraph "Migration of clause-derived gap ids" in the detect-impl-gaps contract, which already states the migration duty; this proposal only replaces its verification bar, so no new clause is added.

### Proposed Changes

Three edits to `SPECIFICATION/contracts.md` and one to `SPECIFICATION/scenarios.md`. All land in one revision. No `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

**1. `contracts.md`, the paragraph that begins "**Migration of clause-derived gap ids.**".** Replace its third sentence, which today reads:

```
Every live such item MUST be re-labelled with the heading-derived gap-id
of the heading its clause sits under, and the implementation of this
clause MUST NOT be reported complete until that re-labelling has run, so
livespec core's `gap-tracking-one-to-one` and `no-stale-gap-tied`
invariants pass on this repository against the new enumeration.
```

with:

```
Every live such item MUST be re-labelled with the heading-derived gap-id
of the heading its clause sits under, and the implementation of this
clause MUST NOT be reported complete until that re-labelling has run and
both of the following hold on this repository against the new
enumeration: no gap-id is carried by more than one live gap-tied
work-item, and every live gap-tied work-item carries a gap-id that
`detect-impl-gaps --json` emits. These are verified against this
plugin's own `list-work-items --json` and `detect-impl-gaps --json`
output; livespec core's doctor no longer carries a gap check.
```

The paragraph's other sentences ("A gap-tied work-item filed under the retired clause enumeration...", "The detector change and the live re-labelling MAY land as separate changes, in that order.", "A closed item MUST keep its historical clause-derived label.") are unchanged.

**2. `contracts.md`, the detect-impl-gaps "Consumers:" list.** Delete its first bullet in full:

```
- `livespec` doctor's `gap-tracking-one-to-one` and `no-stale-gap-tied`
  invariants subprocess this skill via the
  `<impl-plugin>:detect-impl-gaps --json` cross-boundary handoff (per
  upstream §"Cross-boundary handoffs" entry 5).
```

The remaining bullets (the heavyweight `capture-impl-gaps` sibling, and the `implement` skill's check-path-anchored closure) are unchanged and keep their order.

**3. `contracts.md`, `## Cross-boundary handoffs`.** Delete entries 2 and 3 of the numbered list:

```
2. `/livespec:doctor` → `/livespec-orchestrator-beads-fabro:list-work-items --json`
   (work-item structural invariants).
3. `/livespec:doctor` → `/livespec-orchestrator-beads-fabro:detect-impl-gaps --json`
   (gap-detection invariants `gap-tracking-one-to-one` and
   `no-stale-gap-tied`).
```

Entry 1 (`/livespec-orchestrator-beads-fabro:capture-spec-drift` → `/livespec:propose-change`) remains as the list's only entry, numbered 1. The paragraph that follows ("The handoff mechanism is namespace invocation...") is unchanged.

**4. `scenarios.md`, the scenario "Clause-derived gap ids are migrated to heading-derived ones".** Replace the step:

```
    And livespec core's gap-tracking-one-to-one and no-stale-gap-tied invariants pass
```

with the two steps:

```
    And no gap-id is carried by more than one live gap-tied work-item
    And every live gap-tied work-item carries a gap-id that detect-impl-gaps --json emits
```

The scenario's Given, When, its first Then and its final step ("And a closed item keeps its historical clause-derived label") are unchanged.
