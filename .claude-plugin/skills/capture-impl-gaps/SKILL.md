---
name: capture-impl-gaps
description: Detect spec→impl gaps by invoking the sibling detect-impl-gaps thin-transport skill, then file gap-tied work-items into the beads-backed store with per-gap user consent. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)". Invoke as `/livespec-orchestrator-beads-fabro:capture-impl-gaps`.
allowed-tools: Bash, Read, Grep, Glob, Write
---

# capture-impl-gaps

Mechanical detection of spec→impl gaps. Heavyweight skill — orchestration
lives here in the SKILL.md prose per
SPECIFICATION/constraints.md §"Skill orchestration constraints". The
plugin's `detect-impl-gaps` thin-transport sibling and `store` module are
the load-bearing surfaces this skill composes.

## Pre-requisites

- The consumer project has a `<spec-root>/` directory at the path
  declared in `.livespec.jsonc` (default: `SPECIFICATION/`).
- The `livespec-orchestrator-beads-fabro` Python package is on the import path.
  The shipped wrappers self-bootstrap this: `bin/_bootstrap.py` adds
  `scripts/` and `scripts/_vendor/` to `sys.path`, so each
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/<name>.py"` invocation
  resolves `livespec_orchestrator_beads_fabro` and the vendored
  `livespec_runtime` with no `uv` and no project venv.
- The work-items JSONL store path is reachable (created on first
  append if absent).

## Flow

### Step 1 — Enumerate gap candidates via detect-impl-gaps

Invoke the sibling thin-transport skill `detect-impl-gaps` to retrieve
the authoritative gap-id set. Per SPECIFICATION/contracts.md
§"capture-impl-gaps", both this skill and the doctor invariants consume
the same canonical surface; in-skill duplication of the detection logic
is forbidden.

Run the skill twice — once with `--json` for the authoritative gap-id
set, once without for the rich line form used to surface each candidate
to the user in Step 2:

```bash
# Authoritative gap-id set:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/detect_impl_gaps.py" --json
# → {"gap_ids": ["gap-abc123", "gap-def456", ...]}

# Rich human-readable context for display:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/detect_impl_gaps.py"
# → each line: <spec-file> > <heading-path>  [<gap_id>]  <rule-text>
```

Both invocations use the same canonical `detect_rules` function and
emit deterministically-sorted output, so the two outputs can be joined
by `gap_id` to produce a candidate list of
`(gap_id, spec_file, heading_path, rule_text)` tuples. The `--json`
form is the authoritative set; the rich form is convenience metadata
for human display.

#### Optional `--since-version <vN>` scoping

`capture-impl-gaps` accepts an optional `--since-version <vN>` flag
and passes it through verbatim to BOTH `detect-impl-gaps` invocations
above. When set, gap detection is restricted to spec files whose
content differs between historical version `<vN>` and the live spec.

```bash
# Scoped to changes introduced since v082:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/detect_impl_gaps.py" --json --since-version v082
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/detect_impl_gaps.py" --since-version v082
```

The flag is the user-facing surface that callers (notably
`/livespec:revise`'s post-step per the parent coordinating epic,
livespec PC `revise-post-step-capture-impl-gaps`) use to scope
per-revise gap detection to the diff that revise just introduced.
Direct user invocations MAY use it for any "show me gaps for changes
since this version" workflow.

Validation is delegated to `detect-impl-gaps`. If the value is
invalid:

- Non-integer / non-positive input → `detect-impl-gaps` exits `2`
  with a usage error.
- Missing version directory (`<spec-root>/history/v<padded-N>/`
  does not exist) → `detect-impl-gaps` exits `3` with a
  `SpecVersionNotFoundError` message.

In either case, `capture-impl-gaps` surfaces the error to the user
and aborts before reaching Step 2; no work-items are filed.

When `--since-version` is omitted, behavior is unchanged — every
file in the live spec is scanned.

### Step 2 — Per-rule gap classification

For each candidate, ask the user:

> Is the implementation honoring this rule? (yes / no / skip)

- `yes` — no gap; move on.
- `no` — a gap exists. Proceed to Step 3.
- `skip` — defer judgment; move on without filing.

### Step 3 — Per-gap consent + filing

For each `no` rule, the `gap_id` is already in hand from Step 1 (derived
inside `detect-impl-gaps` from `<spec-file>\x1f<heading-path>\x1f<rule-text>`
hashing; shape `gap-<8-char-base32-suffix>`). Then:

1. Check the work-items store: if a record with this `gap_id` already
   exists and is not closed, surface "already filed as `<li-id>`" and
   skip filing.
2. Otherwise, ask the user to confirm title + description (auto-drafted
   from the rule text). Defaults are pre-filled; the user accepts or
   edits.
3. On confirm, append a new work-item JSONL record:

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
    type="task",
    status="open",
    title=user_confirmed_title,
    description=user_confirmed_description,
    origin="gap-tied",
    gap_id=gap_id,
    priority=2,
    assignee=None,
    depends_on=(),
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)
append_work_item(path=config, item=item)
```

#### Intake Definition-of-Ready (per filed gap)

Every capture front-end MUST run the intake Definition-of-Ready
checklist at capture and tag the filed item `ready`, `needs-regroom`,
or `not-yet-actionable` (SPECIFICATION/scenarios.md "Scenario 8 —
Intake Definition-of-Ready triage"; contracts.md §"Gap-detectable
behavior clauses"). The gate logic is the ONE shared
`livespec_orchestrator_beads_fabro.intake_dor` primitive — never re-derive the gates
in prose here.

Immediately after filing each gap-tied item, resolve the six gates from
the gap context (the rule text usually names a single coherent "done"
and a repo target) plus a short confirmation, then stamp the verdict:

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

Narrate the verdict: `ready` is dispatch-eligible; `needs-regroom`
surfaces the item for grooming (`groom <id>`, via the shared
`regroom.enter`) instead of filing it `ready`; `not-yet-actionable`
means the acceptance needs a human judgement call, an unresolved blocker
remains, or a dispatch facet is missing — it MUST NOT be filed `ready`.

### Step 4 — Summary

When all candidates are processed, print a summary:

- N candidate rules surfaced
- M classified as gaps, of which K were newly filed and J were already-tracked
- Skipped: S

## Important properties

- **In-memory ephemeral detection state** — no persistent intermediate
  artifact. The candidate list is discarded at skill exit per
  livespec/SPECIFICATION/contracts.md §"Heavyweight authored
  skills (6)" → capture-impl-gaps.
- **Per-gap user consent is REQUIRED** — never auto-file without
  explicit confirmation.
- **Idempotent** — re-running surfaces no duplicates for gaps already
  tracked (status≠closed).
- **No LLM in the detection path itself** — pattern-matching of MUST /
  SHOULD clauses is deterministic. LLM dialogue is used only for the
  classification and authoring steps (and only with user-in-the-loop).

## What this skill does NOT do

- Does NOT close work-items. Use `implement` for that.
- Does NOT modify the spec tree (all spec reads are delegated to
  `detect-impl-gaps`).
- Does NOT detect impl→spec drift. That's `capture-spec-drift`.
