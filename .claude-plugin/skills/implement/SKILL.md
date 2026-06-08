---
name: implement
description: Drive Red→Green for a single work-item. For gap-tied items, verify closure by re-running capture-impl-gaps in dry-run mode. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)". Invoke as `/livespec-impl-beads:implement [<work-item-id>]`.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
---

# implement

The Red→Green driver. Walks a single work-item from open through
implementation to closed-with-audit. Closure branches on `origin ×
disposition` per livespec/SPECIFICATION/contracts.md
§"Heavyweight authored skills (6)" → implement.

## Pre-requisites

- A work-item to drive. Either passed by id (positional argument) or
  derived from `next` if none given.
- The work-items JSONL store path is reachable.
- Tests pass on the current branch (Red is fine; mid-cycle is not).
- `just check` exists in the consumer project (or equivalent toolchain
  command).

## Flow

### Step 1 — Pick the work-item

If `<work-item-id>` was supplied, load it from the JSONL store:

```python
from livespec_impl_beads.store import materialize_work_items, read_work_items
from pathlib import Path

ix = materialize_work_items(read_work_items(path=Path("work-items.jsonl")))
target = ix[work_item_id]
```

If no id was supplied, invoke `/livespec-impl-beads:next --json`,
parse the `work_item_ref`, and confirm with the user before
proceeding.

Refuse to proceed if `target.status != "open"`. Surface a clear error
and exit.

### Step 2 — Disposition decision

Ask the user up-front:

> Resolution path for this work-item:
> 1. Completed (Red→Green; this is the default)
> 2. wontfix / duplicate / spec-revised / no-longer-applicable /
>    resolved-out-of-band

For path 1, proceed to Step 3. For path 2, jump to Step 6 (admin
closure).

### Step 3 — Red

Author a failing test that exercises the work-item's intent:

- Identify the test file location (mirrors source tree).
- Write the test; ensure it fails for the reason described in the
  work-item.
- Commit the failing test with the `RED:` trailer convention (or the
  consumer project's red-green-replay convention).

### Step 4 — Green

Implement until the test passes:

- Make the smallest change that turns the failing test green.
- Run `just check` (or the consumer's check command) to confirm the
  full enforcement suite passes.
- Commit the impl.

### Step 5 — Closure verification

#### Step 5a — Gap-tied closure verification

When `target.origin == "gap-tied"`, the closure REQUIRES re-running
`capture-impl-gaps` in dry-run mode and confirming the `gap_id` is no
longer detected. v001 starter: surface to the user "please re-run
capture-impl-gaps and confirm the gap is gone" and ask `confirmed?`.
Future revisions will automate the dry-run invocation.

If the gap is still detected, the work-item is NOT closed — the user
either revises the impl further (back to Step 4) or marks the
work-item with one of the admin resolutions (Step 6).

#### Step 5b — Freeform closure

When `target.origin == "freeform"`, no re-detection runs. Proceed
directly to closure.

### Step 6 — Append closure record

Append a new JSONL record with `status: closed`. The exact shape
branches on the resolution choice:

```python
from livespec_impl_beads.store import append_work_item
from livespec_impl_beads.types import AuditRecord, WorkItem
from datetime import datetime, timezone
from pathlib import Path

audit = (
    AuditRecord(
        verification_timestamp=datetime.now(tz=timezone.utc).isoformat(),
        commits=tuple(verified_commit_shas),
        files_changed=tuple(verified_files),
    )
    if resolution == "completed" and target.origin == "gap-tied"
    else None
)

closing_record = WorkItem(
    id=target.id,
    type=target.type,
    status="closed",
    title=target.title,
    description=target.description,
    origin=target.origin,
    gap_id=target.gap_id,
    priority=target.priority,
    assignee=target.assignee,
    depends_on=target.depends_on,
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    resolution=resolution,
    reason=user_supplied_reason,
    audit=audit,
    superseded_by=None,
)
append_work_item(path=Path("work-items.jsonl"), item=closing_record)
```

Print "closed `<id>` (`<resolution>`)" to the user.

## Important properties

- **Same `id`, new record** — closure does NOT mutate the open record.
  It appends a new record with the same `id`; the materialized view
  (latest-record-wins) shows the closed state.
- **Audit fields REQUIRED for gap-tied completed closure** —
  `verification_timestamp`, `commits`, `files_changed`. Doctor catches
  missing audits.
- **Admin closures take a `reason`** — `wontfix`, `duplicate`,
  `spec-revised`, `no-longer-applicable`, `resolved-out-of-band` all
  require a user-supplied `reason` field.
- **`completed` closure on `freeform` items takes a simple `reason`** — no
  audit object needed.

## What this skill does NOT do

- Does NOT modify the spec tree.
- Does NOT auto-supersede related items. The user MAY supersede
  manually via a fresh `capture-work-item` referencing the closed id
  in `description`.
- Does NOT skip the test step. Red→Green is the rule; emergency
  closure paths are `wontfix` / `resolved-out-of-band` resolutions,
  not test-skipping.
