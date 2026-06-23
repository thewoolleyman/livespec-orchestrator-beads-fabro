# capture-spec-drift

Harness-neutral driving prose for the `capture-spec-drift` operation,
per `SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the consent flow, the multi-step dialogue, the
`livespec_orchestrator_beads_fabro.*` package calls, and the
cross-boundary propose-change handoff semantics. Each per-runtime
SKILL.md is a THIN binding that resolves the plugin root, reads this
prose in full, and maps its harness-neutral vocabulary (the
"ask the user" / "read the file" verbs, the propose-change operation
handoff) to that runtime's tools. Nothing in this file names a specific
agent runtime's tools or command namespace.

Asymmetric counterpart to `capture-impl-gaps`. Where impl-gap detection
is mechanical, drift detection is heuristic — the implementation may
have evolved beyond what the spec documents, in ways no static
pattern-match can flag. The operation drives an LLM-assisted comparison
between the canonical Specification (via the Spec Reader) and the
working impl tree, surfaces each candidate finding to the user, and
hands the confirmed findings off to the propose-change operation
via the cross-boundary handoff (red-edge handoff 1 per
livespec/SPECIFICATION/contracts.md §"Cross-boundary handoffs").

## Pre-requisites

- A `<spec-root>/` containing ratified spec content at the path
  declared in `.livespec.jsonc` (default: `SPECIFICATION/`).
- The consumer project's impl tree (the rest of the repo besides
  `<spec-root>/`).
- livespec installed and accessible — the propose-change cross-boundary
  handoff requires it.

## Flow

### Step 1 — Load the comparison baseline

Use the Spec Reader to load the current specification:

```python
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from pathlib import Path

snapshot = read_current_specification(spec_root=Path("SPECIFICATION"))
```

The snapshot is the "what the project says it does." The impl tree is
"what the project actually does." Drift is the delta.

### Step 2 — Survey the impl tree

Scan the consumer project's impl tree (excluding `<spec-root>/`,
`.venv/`, `_vendor/`, generated artifacts) for:

- Public API surfaces (function signatures, CLI flag declarations,
  config schema entries, REST/gRPC endpoint definitions, etc.).
- Behavior documented inline in code (docstrings, comments tagged
  `# spec:`, etc.).
- Tests that assert behavior visible to external consumers.

For each candidate, ask:

> Is this behavior reflected in the Specification? (yes / no / partial / skip)

- `yes` — no drift; move on.
- `no` — drift exists; behavior is not in the spec. Proceed to Step 3.
- `partial` — drift exists; spec captures some but not all of the
  behavior. Proceed to Step 3 with a "refinement" framing.
- `skip` — defer judgment.

### Step 3 — Per-finding propose-change handoff

For each `no` / `partial` finding:

1. Draft a one-sentence proposed-change framing the missing behavior.
2. Surface it to the user with the recommended action ("file a propose-change
   targeting `<spec-root>/`?").
3. On consent, invoke the propose-change operation as the cross-boundary
   handoff:

```bash
the propose-change operation --spec-target SPECIFICATION/ --topic <slug> --body <draft>
```

The proposed-change file lands under `<spec-root>/proposed_changes/`
awaiting a subsequent revise pass.

### Step 4 — Summary

When all candidates are processed, print a summary:

- N impl behaviors surveyed
- M classified as drift, of which K were filed as propose-changes
- S skipped

## Important properties

- **LLM-assisted, user-in-the-loop** — every drift finding requires
  explicit user consent before a propose-change is filed. The operation
  does NOT auto-file.
- **Read-only on the impl tree** — the operation never modifies source
  code. Spec authorship happens through the propose-change operation,
  not here.
- **Spec-side write goes through the cross-boundary handoff** — this
  plugin never writes to `<spec-root>/proposed_changes/` directly. The
  handoff invocation is the surface contract.

## What this operation does NOT do

- Does NOT modify the impl tree.
- Does NOT modify the spec tree directly. Routes through
  the propose-change operation.
- Does NOT detect spec→impl gaps. That's the `capture-impl-gaps`
  operation.
- Does NOT auto-accept findings. User confirms every handoff.
