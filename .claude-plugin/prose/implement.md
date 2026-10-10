# implement

Per `SPECIFICATION/constraints.md` §"Skill orchestration constraints", this is the harness-neutral operation prose; each runtime binding only maps its tools to it.

## What done looks like

Done is closure with the Definition of Done proved, an administrative resolution, or rest in
acceptance on a pending host leg; each outcome is reported as what it is.

This Red→Green driver walks one work-item through the disposition and closure rules in
`SPECIFICATION/contracts.md` §"Heavyweight authored skills (5)" → implement.

## Pre-requisites

- A work-item to drive. Either passed by id (positional argument) or
  derived from the `next` operation if none given.
- The beads work-items store is reachable through the repository's resolved tenant connection.
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
2. **Default: dispatch and supervise.** For product-code work, route product-code work through
   `drive` with `impl:<id>` or the Dispatcher drain, then skip the in-session steps below. For a
   dispatch you launch, retain supervision through the detached gate runner and inspect its result.
   Submission alone does not complete the work item; report any remaining acceptance or proof leg.
3. **The in-session exception path.** Drive Red→Green in-session ONLY
   when at least one of the following holds, and record WHICH one (with
   a one-line reason) in the work-item's closure audit:
   - the item is explicitly recorded as **factory-ineligible** (host
     mutation, interactive credentials, or mid-implementation human
     judgment);
   - the **factory is unavailable** (Dispatcher/server outage, or the
     repo is not factory-wired) and the work must not wait;
   - the item is explicitly recorded as a **master-health-restoration**
     item and red master is the condition parking it behind the
     Dispatcher or local commit gate. This is the blessed escape hatch:
     drive the fix in-session through worktree -> PR -> merge, because
     PR CI is independent of master. Do not treat `gh run rerun --failed`
     as a remedy for repeat-flakes; repeated reruns can burn cycles while
     master stays red. If the local pre-commit hook itself refuses every
     commit because master is red, the sanctioned break-glass is a
     server-side GitHub revert: fetch the offending PR's node id with a
     `repository.pullRequest(number:)` GraphQL query, then call
     `revertPullRequest` with that id, passing both the query and the
     mutation body from files. Prefer re-landing the reverted change
     paired with its fix in one PR.
   - the **maintainer explicitly directed** in-session execution for
     this item in this session.
4. **Non-product changesets** (docs, spec prose, plans,
   work-item records, config chores — what the Red-Green-Replay gate
   exempts) are not factory-gated; proceed to Step 1.

### Step 1 — Pick the work-item

If `<work-item-id>` was supplied, load it from the resolved beads tenant:

```python
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
ix = materialize_work_items(read_work_items(path=config))
target = ix[work_item_id]
```

If no id was supplied, defer to the `next` operation (`--json`), parse
the `work_item_ref`, and confirm with the user before proceeding.

Use the livespec lifecycle states rather than an `open` predicate: beads exposes `backlog`, `ready`,
`blocked`, `active`, `acceptance`, `pending-approval`, and `closed` (`done` in the `WorkItem`
projection). Route `backlog` through `groom`, `pending-approval` through its valve, and `ready`
through `drive`; continue in-session only on the Step 0 exception path. Report `blocked`,
`acceptance`, or `closed` as the actual routed state instead of manufacturing a status refusal.

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

When `target.origin == "gap-tied"`, closure is anchored to a CHECK PATH
recorded on the work-item's own beads metadata (`gap_check_path`),
never to `gap_id` — a `gap_id` hashes a hard-wrapped source line and
re-keys on reflow, so it cannot anchor a closure that must survive the
clause being edited or reworded.

If the work-item's metadata does not yet carry a `gap_check_path`, ask
the user which executable check settles this clause — a script
following the `main() -> int` convention (exit 0 = pass, non-zero =
fail) that ALSO accepts a `--negative-control` flag which MUST exit
non-zero (proving the check can fail and is therefore discriminating,
not vacuously true) — and record it:

```python
from livespec_orchestrator_beads_fabro.commands._gap_closure import record_gap_check
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
record_gap_check(
    config=config,
    project_root=Path.cwd(),
    item_id=target.id,
    check_path=user_supplied_check_path,
)
```

At closure, evaluate:

```python
from livespec_orchestrator_beads_fabro.commands._gap_closure import evaluate_gap_closure

decision = evaluate_gap_closure(config=config, project_root=Path.cwd(), item_id=target.id)
```

Branch on `decision.verdict`:

- `"close"` — proceed to Step 6.
- `"refuse-check-failed"` — the recorded check did not pass, or its
  negative control did not fail (not discriminating). The work-item is
  NOT closed — the user either revises the impl further (back to
  Step 4) or fixes the check.
- `"refuse-drift-required"` — the check file was modified since the
  baseline recorded when it was cited (`decision.detail` names this).
  Invoke the `capture-spec-drift` operation's targeted
  `--for-work-item <id>` mode; on the resulting propose-change landing,
  record it:

  ```python
  from livespec_orchestrator_beads_fabro.commands._gap_closure import record_drift_propose_change

  record_drift_propose_change(
      config=config,
      item_id=target.id,
      propose_change_topic=resulting_propose_change_topic,
  )
  ```

  then re-evaluate (`evaluate_gap_closure` again) before closing.
- `"refuse-no-check-recorded"` — record one (above), then re-evaluate.

Never re-run `capture-impl-gaps` or inspect `gap_id` as part of this
step; detection is spec-only and `gap_id` is unsound as a closure
anchor.

#### Step 5b — Freeform closure

When `target.origin == "freeform"`, no re-detection runs. Proceed
directly to closure.

### Step 6 — Close through the beads store

Write the consented resolution through the shared beads lifecycle seam. The logical `done` status
maps to beads-native `closed`; the exact shape branches on the resolution choice:

```python
from dataclasses import replace
from datetime import datetime, timezone
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    close_work_item_and_reconcile,
)
from livespec_orchestrator_beads_fabro.types import AuditRecord

audit = (
    AuditRecord(
        verification_timestamp=datetime.now(tz=timezone.utc).isoformat(),
        commits=tuple(verified_commit_shas),
        files_changed=tuple(verified_files),
    )
    if resolution == "completed" and target.origin == "gap-tied"
    else None
)

closing_record = replace(
    target,
    status="done",
    resolution=resolution,
    reason=user_supplied_reason,
    audit=audit,
)
close_work_item_and_reconcile(path=config, item=closing_record)
```

Print "closed `<id>` (`<resolution>`)" to the user.

## Important properties

- **Closure writes are user-consented** — the Step 2 resolution-path
  decision (plus the Step 5a check-path verification for gap-tied
  items) is the per-operation consent for the Step 6 closure write
  (per SPECIFICATION/contracts.md §"Store-write consent discipline");
  no closure record is written without it.
- **Same `id`, in-place beads closure** — the shared store seam retains the item identity while
  applying the closed status, resolution label, audit metadata, and run reconciliation.
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
