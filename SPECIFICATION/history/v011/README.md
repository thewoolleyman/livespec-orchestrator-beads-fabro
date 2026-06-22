# livespec-orchestrator-beads-fabro — SPECIFICATION/

This directory holds the natural-language specification for
`livespec-orchestrator-beads-fabro`. Per
livespec/SPECIFICATION/non-functional-requirements.md
§"Implementation plugin ecosystem", every `livespec-impl-*` plugin
MUST dogfood its own `SPECIFICATION/` and MUST conform to the
implementation-plugin contract published by `livespec`.

## Bootstrapping

To populate the spec tree, run from this repo's root:

```
/livespec:seed --spec-target SPECIFICATION/
```

The seed wrapper writes the canonical NLSpec multi-file convention:

- `spec.md` — overall intent and behavior
- `contracts.md` — wire-level interfaces (the 7-skill surface, the
  Spec Reader internal adapter, the work-items store schema,
  the `compat` block this plugin pins against `livespec`)
- `constraints.md` — architecture-level constraints
- `scenarios.md` — behavioral narratives
- `proposed_changes/` — queue of pending proposals
- `history/v001/` — initial revision snapshot

## Required content

Per `livespec/SPECIFICATION/contracts.md`, this spec MUST
document:

- The plugin's seven-skill surface (four heavyweight authored skills:
  capture-impl-gaps, capture-spec-drift, capture-work-item, implement;
  three thin-transport skills: detect-impl-gaps, list-work-items, next)
- The Spec Reader internal API's four required capabilities
- The work-items store schema and its on-disk layout
- The Persistent Agent Knowledge store realization for this plugin
- The `compat` block declaring this plugin's `livespec` semver
  range and pinned release tag

## Lifecycle

After seed, evolve the spec through the standard livespec
sub-commands:

- `/livespec:propose-change --spec-target SPECIFICATION/`
- `/livespec:critique --spec-target SPECIFICATION/`
- `/livespec:revise --spec-target SPECIFICATION/`
- `/livespec:doctor --spec-target SPECIFICATION/`
- `/livespec:prune-history --spec-target SPECIFICATION/`
- `/livespec:next --spec-target SPECIFICATION/`

This README is a placeholder — once `/livespec:seed` runs it
will be replaced (or co-exist depending on the template's `README.md`
slot rules).
