---
name: process-memos
description: Per-memo handholding dialogue with four canonical dispositions — spec-bound, impl-bound, persistent-knowledge, discard. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)". Invoke as `/livespec-impl-beads:process-memos`.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
---

# process-memos

The drain half of the memo lifecycle. Iterates over untriaged memos
and routes each to its canonical disposition per
livespec/SPECIFICATION/spec.md §"Disposition (memo)". The four
dispositions are mutually exclusive; every memo lands in exactly one.

## Pre-requisites

- The memos JSONL store path is reachable.
- `livespec` installed (the spec-bound disposition requires the
  `/livespec:propose-change` cross-boundary handoff).
- The consumer project has `CLAUDE.md` and/or `AGENTS.md` at the root
  (the persistent-knowledge disposition writes references into them).

## Flow

### Step 1 — Load the untriaged queue

Use the existing list-memos thin-transport skill, or invoke
materialize_memos directly:

```python
from livespec_impl_beads.store import materialize_memos, read_memos
from pathlib import Path

memos = list(materialize_memos(read_memos(path=Path("memos.jsonl"))).values())
untriaged = [m for m in memos if m.state == "untriaged"]
```

If the queue is empty, surface "no untriaged memos" and exit cleanly
(rc=0).

### Step 2 — Per-memo dialogue

For each untriaged memo, in order of `captured_at` (oldest first):

1. **Show** — print id, captured_at, full text.
2. **Ask** — "Disposition?":
   - `1. spec-bound` → propose-change handoff
   - `2. impl-bound` → freeform work-item
   - `3. persistent-knowledge` → `.ai/<topic>.md` graduation
   - `4. discard` → state marker only
   - `5. skip` → leave untriaged, move on (NOT a final disposition)
3. **Branch** to the disposition handler (Step 3a-d).

### Step 3a — spec-bound

The memo content belongs in the Specification.

1. Ask the user for a propose-change topic slug (kebab-case).
2. Invoke the cross-boundary handoff (red-edge entry 2 per
   livespec/SPECIFICATION/contracts.md §"Cross-boundary
   handoffs"):

```bash
/livespec:propose-change --spec-target SPECIFICATION/ \
    --topic <slug> --body "<memo-text>"
```

3. Append a closing memo record with `state: dispositioned`,
   `disposition: spec-bound`, `propose_change_topic: <slug>`. Same id
   as the original memo; materialized view shows the dispositioned
   state.

### Step 3b — impl-bound

The memo content is a freeform impl-side work-item (bug, refactor,
tactical task).

1. Invoke `/livespec-impl-beads:capture-work-item` internally with
   the memo text pre-filled as the description (user confirms title /
   type / priority).
2. Capture the resulting `work_item_id`.
3. Append a closing memo record with `state: dispositioned`,
   `disposition: impl-bound`, `work_item_id: <li-id>`.

### Step 3c — persistent-knowledge

The memo content is long-term agent guidance.

1. Ask the user for a topic name (kebab-case, e.g.,
   `mise-exec-for-git-hooks`).
2. Check if `.ai/<topic>.md` exists:
   - If yes — append the memo content as a new section under a
     heading dated `## <captured_at-date>`.
   - If no — create the file with a top-level heading derived from the
     topic, followed by the memo content under the same dated section
     heading.
3. Verify `CLAUDE.md` (and/or `AGENTS.md`) reference the file via a
   bullet of the form `- [.ai/<topic>.md](.ai/<topic>.md) — <one-line
   summary>`. If not present, append the bullet to a "Persistent Agent
   Knowledge" section (creating the section if absent).
4. Append a closing memo record with `state: dispositioned`,
   `disposition: persistent-knowledge`, `knowledge_file:
   ".ai/<topic>.md"`.

### Step 3d — discard

The memo content does NOT belong in spec, impl, or persistent
knowledge.

1. Ask the user for a brief discard reason (optional).
2. Append a closing memo record with `state: dispositioned`,
   `disposition: discard`. The memo `text` stays on disk (audit-trail
   discipline per SPECIFICATION/constraints.md §"Forbidden patterns":
   "no memo deletion"); only the state marker changes.

### Step 4 — Summary

When the queue is drained (or the user exits via `skip` on all
remaining), print a per-disposition count:

```
processed N memos:
  spec-bound: K (filed as propose-changes)
  impl-bound: J (filed as work-items)
  persistent-knowledge: L (graduated to .ai/ files)
  discard: M
remaining untriaged: P
```

## Important properties

- **One memo, one disposition** — every memo eventually lands in
  exactly one of the four canonical dispositions; `skip` is a
  loop-control choice, not a disposition.
- **Append-only** — the closing record carries the same `id` as the
  original; both records remain on disk for audit.
- **persistent-knowledge graduation is BIDIRECTIONAL** — the
  `.ai/<topic>.md` file MUST be referenced from `CLAUDE.md` /
  `AGENTS.md` (orphaned files are forbidden by
  SPECIFICATION/constraints.md §"Persistent Agent Knowledge
  constraints").
- **Cross-boundary handoff is namespace-scoped** — invoke
  `/livespec:propose-change`, never `python3
  ~/.claude/plugins/.../bin/propose_change.py`. Discoverability
  through the slash command is the contract.

## What this skill does NOT do

- Does NOT auto-discard. Every disposition is user-confirmed.
- Does NOT delete memo records. `discard` is a state transition, not
  a removal.
- Does NOT modify the Specification. The spec-bound disposition
  routes through `/livespec:propose-change`, which is the only
  permitted spec-write surface.
- Does NOT graduate persistent-knowledge content silently — the
  `CLAUDE.md` / `AGENTS.md` reference is part of the disposition
  contract.
