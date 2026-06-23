# capture-work-item

Harness-neutral driving prose for the `capture-work-item` operation,
per `SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the consent flow, the multi-step dialogue, the
`livespec_orchestrator_beads_fabro.*` package calls, and the JSON /
handoff semantics. Each per-runtime SKILL.md is a THIN binding that
resolves the plugin root, reads this prose in full, and maps its
harness-neutral vocabulary (the `<plugin-root>` token, the
"ask the user" / "read the file" / "write the file" verbs, the named
sibling operations) to that runtime's tools. Nothing in this file
names a specific agent runtime's tools or command namespace.

The freeform direct-filing operation. Use this for bugs, refactors,
tactical tasks, and anything else that doesn't trace back to a spec
rule. For spec-traceable items, use the `capture-impl-gaps` operation
instead.

## Pre-requisites

- The work-items JSONL store path is reachable.
- `livespec_orchestrator_beads_fabro` package on import path.

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
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem
from datetime import datetime, timezone
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
item = WorkItem(
    # The id-prefix is the tenant's server-stored bd create-prefix
    # (config.prefix), DECOUPLED from the tenant DB name — so the id
    # carries config.prefix, not a hardcoded `li-`.
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

### Step 3 — Run the intake Definition-of-Ready checklist

Every capture front-end MUST run the intake Definition-of-Ready
checklist at capture and tag the filed item `ready`, `needs-regroom`,
or `not-yet-actionable` (SPECIFICATION/scenarios.md "Scenario 8 —
Intake Definition-of-Ready triage"; contracts.md §"Gap-detectable
behavior clauses"). The gate logic is the ONE shared
`livespec_orchestrator_beads_fabro.intake_dor` primitive — never re-derive the gates
in prose here.

Resolve the six gates from the inputs you already gathered plus a short
confirmation dialogue (one question at a time; many gates are already
answerable from Step 1):

- `single_coherent_done` — does the item describe exactly ONE coherent
  "done"? (more than one ⇒ an epic ⇒ `needs-regroom`)
- `autonomously_verifiable` — can the acceptance be checked WITHOUT a
  human judgement call?
- `autonomy_tiered` — does the item carry an explicit autonomy tier?
- `dependency_linked` — are its blockers linked (the `depends_on` set),
  or does it genuinely have none?
- `repo_targeted` — does it name the repo it lands in?
- `above_floor` — is it above the size floor (worth a discrete
  dispatch)?

Then stamp the verdict on the just-filed item:

```python
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)

verdict = apply_intake_dor(
    path=config,
    item_id=item.id,
    checklist=DefinitionOfReadyChecklist(
        single_coherent_done=single_coherent_done,
        autonomously_verifiable=autonomously_verifiable,
        autonomy_tiered=autonomy_tiered,
        dependency_linked=dependency_linked,
        repo_targeted=repo_targeted,
        above_floor=above_floor,
    ),
)
# verdict is one of "ready" / "needs-regroom" / "not-yet-actionable".
```

Narrate the verdict to the user:

- `ready` — eligible for autonomous dispatch.
- `needs-regroom` — an epic; surfaced for grooming (run the `groom`
  operation), NOT filed `ready`. The label is applied via the shared
  `regroom.enter` verb.
- `not-yet-actionable` — its acceptance needs a human judgement call, it
  has an unresolved blocker, or it is missing a dispatch facet; it is
  NOT auto-dispatched and MUST NOT be filed `ready`.

## Important properties

- **`origin: freeform`** — never `gap-tied`. Use the `capture-impl-gaps`
  operation for gap-traceable items.
- **`gap_id: null`** — REQUIRED. The schema check fires on any
  non-null value combined with `origin: freeform`.
- **Closure path** — closed via the `implement` operation's freeform
  fix path (a user-supplied `--reason` with no re-detection step).

## What this operation does NOT do

- Does NOT close work-items. Use the `implement` operation.
- Does NOT detect gaps. Use the `capture-impl-gaps` operation.
- Does NOT auto-set `assignee` or `depends_on`. User supplies both.
