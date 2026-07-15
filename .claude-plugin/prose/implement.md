# implement

Harness-neutral driving prose for the `implement` operation, per
`SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the disposition/consent flow, the Red→Green driving steps, the
gap-tied closure re-detection, the `livespec_orchestrator_beads_fabro.*`
package calls, and the closure-record semantics. Each per-runtime
SKILL.md is a THIN binding that resolves the plugin root, reads this
prose in full, and maps its harness-neutral vocabulary (the
`<plugin-root>` token, the "ask the user" / "read the file" / "write
the file" verbs, the named sibling operations) to that runtime's
tools. Nothing in this file names a specific agent runtime's tools or
command namespace.

The Red→Green driver. Walks a single work-item from open through
implementation to closed-with-audit. Closure branches on `origin ×
disposition` per livespec/SPECIFICATION/contracts.md
§"Heavyweight authored skills (5)" → implement.

## Pre-requisites

- A work-item to drive. Either passed by id (positional argument) or
  derived from the `next` operation if none given.
- The work-items JSONL store path is reachable.
- Tests pass on the current branch (Red is fine; mid-cycle is not).
- `just check` exists in the consumer project (or equivalent toolchain
  command).

## Flow

### Step 0 — Factory routing (dispatch-first)

**"The factory path" means exactly one thing: dispatch through the
Dispatcher — the `drive` operation's `impl:<id>` action or the
Dispatcher's own drain of `ready` items.** The in-session Red→Green
driver below is NOT the factory path, and any handoff or prose that
describes in-session implementation as "the factory path" is defective
(the `plan` operation's handoff gate refuses it).

Resolve the routing before driving anything in-session:

1. **Factory-worker context.** When this operation is running INSIDE a
   factory sandbox clone (the declared sandbox marker is present:
   `git config --get livespec.sandboxExempt` prints `true`), skip this
   step — the session IS the factory-side implementer; proceed to
   Step 1.
2. **Default: dispatch and stop.** When the work-item's implementation
   would change product code (any changeset the repo's Red-Green-Replay
   gate classifies as product), route it factory-side: hand the item to
   the `drive` operation (action `impl:<id>`), or leave it for the
   Dispatcher drain, and STOP — the in-session driver below does not
   run. Monitor the dispatched run instead.
3. **The in-session exception path.** Drive Red→Green in-session ONLY
   when at least one of the following holds, and record WHICH one (with
   a one-line reason) in the work-item's closure audit:
   - the item is explicitly recorded as **factory-ineligible** (host
     mutation, interactive credentials, or mid-implementation human
     judgment);
   - the **factory is unavailable** (Dispatcher/server outage, or the
     repo is not factory-wired) and the work must not wait;
   - the **maintainer explicitly directed** in-session execution for
     this item in this session.
4. **Non-product changesets** (docs, spec prose, plan threads,
   work-item records, config chores — what the Red-Green-Replay gate
   exempts) are not factory-gated; proceed to Step 1.

### Step 1 — Pick the work-item

If `<work-item-id>` was supplied, load it from the JSONL store:

```python
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from pathlib import Path

ix = materialize_work_items(read_work_items(path=Path("work-items.jsonl")))
target = ix[work_item_id]
```

If no id was supplied, defer to the `next` operation (`--json`), parse
the `work_item_ref`, and confirm with the user before proceeding.

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
the `capture-impl-gaps` operation in dry-run mode and confirming the
`gap_id` is no longer detected. v001 starter: surface to the user
"please re-run capture-impl-gaps and confirm the gap is gone" and ask
`confirmed?`. Future revisions will automate the dry-run invocation.

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
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import AuditRecord, WorkItem
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
    rank=target.rank,
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

- **Closure writes are user-consented** — the Step 2 resolution-path
  decision (plus the Step 5a re-detection confirmation for gap-tied
  items) is the per-operation consent for the Step 6 closure write
  (per SPECIFICATION/contracts.md §"Store-write consent discipline");
  no closure record is written without it.
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

## What this operation does NOT do

- Does NOT modify the spec tree.
- Does NOT auto-supersede related items. The user MAY supersede
  manually via a fresh `capture-work-item` operation referencing the
  closed id in `description`.
- Does NOT skip the test step. Red→Green is the rule; emergency
  closure paths are `wontfix` / `resolved-out-of-band` resolutions,
  not test-skipping.
