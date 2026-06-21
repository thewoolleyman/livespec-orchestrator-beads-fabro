---
name: groom
description: Regroom an oversized or non-converging `needs-regroom` work-item into ready, dependency-layered slices. Read-only drafting conversation — the maintainer OWNS the cut and the acceptance; the front-end drafts and files NOTHING until approval. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Skills — augmented versus new" (the one new maintainer surface). Invoke as `/livespec-orchestrator-beads-fabro:groom <work-item-id>`.
allowed-tools: Bash, Read, Grep, Glob
---

# groom

The one new maintainer surface the grooming realization adds: the
agent-drafts / human-approves regroom front-end. Given a `needs-regroom`
item (an intake Definition-of-Ready epic, or a Dispatcher
non-convergence bounce), `groom` drafts a layered decomposition into
`ready` slices, and on the maintainer's approval files those slices and
transitions the original item out — never silently dropping it.

This realizes SPECIFICATION/scenarios.md "Scenario 7 — Regroom an
oversized work-item" and the contracts.md §"Gap-detectable behavior
clauses" groom clause. The mechanical seam is
`livespec_orchestrator_beads_fabro.commands.groom`; the load-bearing state transition
reuses the shared `livespec_orchestrator_beads_fabro.regroom` primitive
(`exit_regroom`), and slice filing reuses `capture-work-item`'s
`append_work_item` machinery — `groom` adds NO new ledger state and no
new store path.

## Pre-requisites

- The target work-item id is at `needs-regroom` (this skill refuses any
  other target).
- The `livespec-orchestrator-beads-fabro` Python package is on the import path.
- `livespec` installed (a spec-change slice routes to
  `/livespec:propose-change`).

## Flow

### Step 1 — Load the read-only grooming context

Confirm the target is actually at `needs-regroom` and read it WITHOUT
mutating anything. `load_groom_context` raises if the id is absent
(`WorkItemNotFoundError`) or not at `needs-regroom`
(`GroomTargetNotRegroomError`) — surface either to the user and stop.

```python
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands.groom import load_groom_context
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
context = load_groom_context(path=config, item_id=item_id)
# context.title / context.description ground the draft in the real item.
```

Then read (read-only) the relevant spec / scenarios and the ledger
(`/livespec-orchestrator-beads-fabro:list-work-items --json`) for surrounding context.

### Step 2 — Draft the layered decomposition (READ-ONLY)

Draft candidate slices. Each candidate is pre-filled with all of:

- **acceptance** — exactly one coherent, autonomously-verifiable "done"
  (a named scenario, or the standing `just check` + `/livespec:doctor`
  gates).
- **autonomy tier** — `factory` (autonomously dispatchable) or
  `human-gated` (a spec change). A spec-change slice is marked
  `is_spec_change=True` and routes to `/livespec:propose-change`, NOT the
  factory.
- **dependency links** — the draft-local TITLE of any EARLIER factory
  slice this one is blocked by (the dependency-layer arrangement).
  Arrange the draft so blockers precede the slices they block.
- **repo target** — the one ledger the slice lands in.
- **scope** — the slice body.

Present the draft to the maintainer. The maintainer OWNS the cut and the
acceptance — `groom` only proposes. The draft is READ-ONLY: nothing is
filed until the maintainer approves. The maintainer may edit the cut /
acceptance / deps / tiers and approve, or send it back to re-draft.

### Step 3 — On approval, file the slices and regroom the original out

ONLY after explicit approval, file the approved factory slices and
transition the original item out of `needs-regroom`:

```python
from livespec_orchestrator_beads_fabro.commands.groom import CandidateSlice, file_approved_slices

result = file_approved_slices(
    path=config,
    regroom_item_id=item_id,
    slices=[
        CandidateSlice(
            title=...,
            description=...,
            acceptance=...,
            autonomy_tier="factory",      # or "human-gated"
            repo_target=...,
            depends_on=(...,),            # earlier factory-slice TITLES
            is_spec_change=False,         # True ⇒ routed, not filed
        ),
        ...
    ],
)
# result.filed_slice_ids        — the `ready` factory slices filed, deps linked.
# result.spec_change_slices     — the human-gated slices to route (Step 4).
# result.regroomed_out is True  — the original left needs-regroom.
```

`file_approved_slices` files each factory slice via the same
`append_work_item` machinery `capture-work-item` uses (tagging each
`ready` and linking its dependency edges), then calls
`regroom.exit_regroom` against the filed slice ids. If the draft files NO
factory slice (an all-spec-change cut), `exit_regroom` REFUSES
(`RegroomExitRefusedError`) and the original STAYS `needs-regroom` —
escalate-don't-drop. A `depends_on` handle naming no earlier factory
slice is a malformed cut (`GroomDraftError`); surface it and re-draft.

### Step 4 — Route the spec-change slices to propose-change

For each entry in `result.spec_change_slices`, invoke the cross-boundary
handoff — these NEVER reach the factory:

```bash
/livespec:propose-change --spec-target SPECIFICATION/ \
    --topic <slug> --body "<slice scope + acceptance>"
```

### Step 5 — Summary

Report: the original item id (now regroomed-out), the filed `ready`
slice ids with their dependency layers, and the spec-change slices routed
to `/livespec:propose-change`. The Dispatcher then drains the `ready`
slices by dependency layer.

## Important properties

- **Read-only until approval** — `load_groom_context` and the drafting
  conversation mutate NOTHING; only `file_approved_slices` (post-approval)
  writes.
- **Escalate-don't-drop** — the original leaves `needs-regroom` ONLY by
  `regroom.exit_regroom` against real filed `ready` slices; an
  all-spec-change cut leaves it `needs-regroom`.
- **No new ledger state, no new store path** — reuses the shared
  `regroom` primitive and `capture-work-item`'s `append_work_item`.
- **Spec-change slices route to `/livespec:propose-change`** — never the
  factory.

## What this skill does NOT do

- Does NOT file anything before the maintainer approves the draft.
- Does NOT close or delete the original item — it transitions it out of
  `needs-regroom` (the item stays in the ledger, regroomed-out).
- Does NOT dispatch slices — the Dispatcher drains the `ready` slices.
- Does NOT detect gaps or drift. Use `capture-impl-gaps` /
  `capture-spec-drift`.
