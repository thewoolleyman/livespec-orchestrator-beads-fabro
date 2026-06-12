# research/

Durable scratch for analyses, measurement baselines, and exploratory
notes that inform future work in this repo without being spec
content. Mirrors the livespec repo's `research/` convention (seeded
here the same way livespec-dev-tooling's `research/` was, by
dev-tooling PR #116).

## What lives here

Subdirectories group docs by topic. As of writing:

- `loop-reflection-gate/` — best-practices survey + design options
  for an eval/audit/reflection gate in the fabro factory loop
  (work-item livespec-impl-beads-895).

## What this directory is NOT

- **Not `SPECIFICATION/`.** Files here are NOT requirements. Anything
  that matures into a rule the system must honor flows through
  `/livespec:propose-change` → `/livespec:revise`.
- **Not `archive/`.** Files there are frozen; files here are living —
  they may be revised, superseded, or deleted as thinking matures.

## When to add a doc

When an investigation produces something worth re-reading later —
a measurement baseline, an audit, a design deliberation — that is
not (yet) a requirement. Markdown, free-form, no required template.
