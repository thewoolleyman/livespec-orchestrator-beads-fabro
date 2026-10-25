---
topic: doctor-no-longer-reads-list-work-items
author: claude-opus-5-5
created_at: 2026-10-25T02:01:53Z
---

## Proposal: Retire the doctor read of list-work-items, which livespec core no longer makes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

livespec core's doctor no longer calls `list-work-items --json`; core retired every work-item invariant in its spec v103. This removes the last doctor → orchestrator cross-boundary handoff entry, retires Scenario 5 (whose only subject is that call), drops the retired `unresolved-spec-commitment` sentence, and removes the doctor-consumer framing from `list-work-items`' and `next`'s flags. Skill behaviour is unchanged.

### Motivation

livespec core retired every work-item doctor invariant in core spec v103 (commit 01c8324b, 2026-06-10). Its `tests/livespec/doctor/static/test___init__.py` pins their absence: `doctor-no-stale-gap-tied`, `doctor-no-duplicate-gap-id`, `doctor-no-orphan-dependency`, `doctor-no-stalled-epic`, `doctor-depends_on-ref-wellformedness` and `doctor-unresolved-spec-commitment` MUST NOT be registered. So no build of core's doctor calls `list-work-items --json`. Spec v212 (PR 3612) removed the matching `detect-impl-gaps` handoff. Its independent reviewer showed the `list-work-items` handoff could not be removed on its own, because Scenario 5 and the `list-work-items` flag text still describe that call, so v212 kept it and deferred this follow-up. This proposal is that follow-up. It deletes the one remaining doctor → orchestrator handoff, the scenario that describes it, the `unresolved-spec-commitment` sentence (a retired invariant on the same surface), and the "doctor" framing on `list-work-items`' and `next`'s flags. It changes no behaviour of either skill. It only stops the spec claiming a consumer that no longer exists. A spec that names a retired consumer as a requirement is unsatisfiable in the same way v212's verification bar was: a work-item whose Definition of Done cites Scenario 5 can never be proved. The scope searched: every `doctor` mention in `SPECIFICATION/{spec,contracts,constraints,scenarios,README}.md` at `0a2b85ae` (44 lines, read individually). The positive control was the known v212-kept entry, `contracts.md:9492`, which the search found.

### Proposed Changes

Five edits in one revision. The removed text is quoted verbatim from SPECIFICATION/ at master `0a2b85ae`.

**1. `contracts.md`, `## Cross-boundary handoffs`.** Delete entry 2 of the numbered list in full:

```
2. `/livespec:doctor` → `/livespec-orchestrator-beads-fabro:list-work-items --json`
   (work-item structural invariants).
```

Entry 1 (`/livespec-orchestrator-beads-fabro:capture-spec-drift` → `/livespec:propose-change`) stays as the list's only entry. The introductory sentence and the "The handoff mechanism is namespace invocation..." paragraph after the list are unchanged.

**2. `contracts.md`, the `capture-work-item` `--spec-commitment-hint` paragraph.** Delete its last sentence:

```
This is the surface livespec's
`unresolved-spec-commitment` doctor invariant queries via
`list-work-items --json` to verify each declared spec→impl commitment
maps to a filed work-item (per
`livespec/SPECIFICATION/contracts.md`).
```

The flag's behaviour (the recorded `spec_commitment_hint` equals the verbatim `id_hint`, and is absent when the flag is omitted) is unchanged, and `list-work-items --with-spec-commitment-hint` still reads it.

**3. `contracts.md`, the `list-work-items` flag text.** Replace the `--project-root` paragraph's last sentence

```
Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.
```

with

```
It lets a caller invoke this skill from outside the consumer
project root.
```

and, in the `--work-items-path` paragraph, replace `(used by tests and by doctor invocations that
want to scope to a non-default store — e.g. the in-memory fake backend)` with `(used by tests and by invocations that
want to scope to a non-default store — e.g. the in-memory fake backend)`.

**4. `contracts.md`, the `next` flag text.** Make the same two replacements in `next`'s `--project-root` and `--work-items-path` paragraphs: replace `Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.` with `It lets a caller invoke this skill from outside the consumer
project root.`, and replace `used by tests and by doctor invocations that want to
scope to a non-default store.` with `used by tests and by invocations that want to
scope to a non-default store.`

**5. `contracts.md`, the work-item beads-issue mapping paragraph.** Replace `so cross-boundary consumers (doctor, the
ranker, the console) see a consistent shape.` with `so cross-boundary consumers (the
ranker, the console) see a consistent shape.`

**6. `scenarios.md`, retire `## Scenario 5 — Doctor cross-boundary read`.** Delete the whole section, from its heading through the closing fence of its gherkin block. Its only subject is doctor's cross-boundary phase invoking `list-work-items --json` for work-item structural invariants, a call no build of livespec core makes. Following the precedent of the already-absent Scenarios 2 and 3, the number is not reused and no other scenario is renumbered. No other spec text cites Scenario 5.

**Heading co-edit.** Removing one `## ` heading requires, in the same change per AGENTS.md "Revise co-edit discipline", dropping its entry from `tests/heading-coverage.json` (today `test: "TODO"`, owner `bd-ib-heat`) and its row from `tests/heading-coverage-debt.json`. No heading is added or renamed.

**Kept, deliberately.** `list-work-items --json` and every flag stay exactly as they are; the drift front-ends, `next`, `needs-attention` and the Dispatcher still consume it. The `contract-version-compatibility` doctor invariant (`## \`compat\` block` and the configuration-block paragraph before `## Cross-boundary handoffs`) is a live core check, so those references stay. The namespace-rename rationale in `## Plugin namespace`, the "Invariants (doctor-checkable; restated for the consumer)" block, and the `no-orphan-blocker` sentence in the beads-issue mapping are out of this proposal's scope; none of them describes a `list-work-items` call.
