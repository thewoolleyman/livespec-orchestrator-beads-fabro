# livespec-orchestrator-beads-fabro — SPECIFICATION/

This directory holds the natural-language specification for
`livespec-orchestrator-beads-fabro`. Per
livespec/SPECIFICATION/non-functional-requirements.md,
every `livespec-impl-*` plugin
MUST dogfood its own `SPECIFICATION/` and MUST conform to the
implementation-plugin contract published by `livespec`.

## Bootstrapping

To populate the spec tree, run from this repo's root:

```
/livespec:seed --spec-target SPECIFICATION/
```

The seed wrapper writes the canonical NLSpec multi-file convention:

- `spec.md` — overall intent and behavior
- `contracts.md` — wire-level interfaces (the 8-skill surface, the
  Spec Reader internal adapter, the work-items store schema,
  the `compat` block this plugin pins against `livespec`)
- `constraints.md` — architecture-level constraints
- `scenarios.md` — behavioral narratives
- `proposed_changes/` — queue of pending proposals
- `history/v001/` — initial revision snapshot

## Required content

Per `livespec/SPECIFICATION/contracts.md`, this spec MUST
document:

- The plugin's skill surface (six heavyweight authored skills:
  capture-impl-gaps, capture-spec-drift, capture-work-item, implement,
  groom, plan;
  one operator skill: orchestrate; three thin-transport skills:
  detect-impl-gaps, list-work-items, next — per `contracts.md`
  §"The skill surface")
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

For maintainer orchestration after bootstrap, use this plugin's
operator surface instead of a manual handoff prompt:

```text
/livespec-orchestrator-beads-fabro:orchestrate plan --repo /path/to/repo --json
/livespec-orchestrator-beads-fabro:orchestrate run --repo /path/to/repo --action <selected-action-id> --json
```

`plan` is read-only and composes spec-side `/livespec:next` with
impl-side `next`. `run` requires an explicit selected action id:
`spec:<action>:<n>` returns a human-gated `/livespec:*` handoff, while
`impl:<work-item-id>` dispatches that existing item through
Dispatcher/Fabro with the default small budget.

This README is a placeholder — once `/livespec:seed` runs it
will be replaced (or co-exist depending on the template's `README.md`
slot rules).
