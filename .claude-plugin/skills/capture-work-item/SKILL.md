---
name: capture-work-item
description: Freeform direct filing of an impl-side work item (bugs, refactors, tactical tasks). Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)". Filed records carry `origin: freeform` and `gap_id: null`. Invoke as `/livespec-impl-beads:capture-work-item`.
allowed-tools: Bash, Read, Grep, Write
---

# capture-work-item

The freeform direct-filing skill. Use this for bugs, refactors,
tactical tasks, and anything else that doesn't trace back to a spec
rule. For spec-traceable items, use `capture-impl-gaps` instead.

## Pre-requisites

- The work-items JSONL store path is reachable.
- `livespec_impl_beads` package on import path.

## Flow

### Step 1 — Gather inputs

Ask the user (one question at a time):

1. **Title** — one-line summary.
2. **Description** — multi-line free-form (markdown permitted).
3. **Type** — one of `bug`, `feature`, `task`, `chore`, `epic`.
4. **Priority** — integer 0–4 (default 2). Re-state semantics if asked:
   0 critical, 1 high, 2 medium, 3 low, 4 backlog.

Optional follow-ups (skip-confirmable):

- **Assignee** — string or null (default null).
- **Depends-on** — comma-separated `li-` ids; empty list permitted.
- **Spec-commitment-hint** — string `id_hint` or null (default null).
  Supplied via `--spec-commitment-hint <id_hint>` when the work-item
  is being filed in response to a spec-side
  `spec_commitments.impl_followups[].id_hint` declaration (per livespec
  `SPECIFICATION/contracts.md` §"Implementation-plugin contract — the
  10-skill surface" → "Work-item `spec_commitment_hint` field"). When
  supplied, the resulting record's `spec_commitment_hint` MUST equal
  the verbatim `id_hint`; when omitted, the field defaults to `null`
  (the freeform case). This is the surface livespec's
  `unresolved-spec-commitment` doctor invariant queries via
  `list-work-items --json` to verify each declared spec→impl
  commitment maps to a filed work-item.

### Step 2 — Confirm and file

Show the user the assembled record and ask "file?". On `yes`, append:

```python
from livespec_impl_beads._ids import new_work_item_id
from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.store import append_work_item
from livespec_impl_beads.types import WorkItem
from datetime import datetime, timezone
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None, memos_arg=None)
item = WorkItem(
    # bd enforces id-prefix == tenant DB name, so the id carries the
    # configured tenant prefix (config.prefix), not a hardcoded `li-`.
    id=new_work_item_id(prefix=config.prefix),
    type=type_,
    status="open",
    title=title,
    description=description,
    origin="freeform",
    gap_id=None,
    priority=priority,
    assignee=assignee,
    depends_on=tuple(depends_on),
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
    spec_commitment_hint=spec_commitment_hint,  # str | None; None for freeform.
)
append_work_item(path=config, item=item)
```

Print the assigned id back to the user.

## Important properties

- **`origin: freeform`** — never `gap-tied`. Use `capture-impl-gaps`
  for gap-traceable items.
- **`gap_id: null`** — REQUIRED. The schema check fires on any
  non-null value combined with `origin: freeform`.
- **Closure path** — closed via `implement`'s freeform fix path (a
  user-supplied `--reason` with no re-detection step).

## What this skill does NOT do

- Does NOT close work-items. Use `implement`.
- Does NOT detect gaps. Use `capture-impl-gaps`.
- Does NOT auto-set `assignee` or `depends_on`. User supplies both.
