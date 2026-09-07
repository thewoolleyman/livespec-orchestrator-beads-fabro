# groom

Harness-neutral driving prose for the `groom` operation, per
`SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the read-only grooming-context load, the agent-drafts / human-approves
decomposition dialogue, the approved-slice filing and explicit original-item
disposition, the spec-change routing, and the
`livespec_orchestrator_beads_fabro.*` package calls. Each per-runtime
SKILL.md is a THIN binding that resolves the plugin root, reads this
prose in full, and maps its harness-neutral vocabulary (the
`<plugin-root>` token, the "ask the user" / "read the file" / "write
the file" verbs, the named sibling operations) to that runtime's
tools. Nothing in this file names a specific agent runtime's tools or
command namespace.

The one new maintainer surface the grooming realization adds: the
agent-drafts / human-approves backlog-decomposition front-end. Given a
`backlog` item (an intake Definition-of-Ready epic, or a Dispatcher
non-convergence bounce), `groom` drafts a layered decomposition. On the
maintainer's approval it files approved factory slices through the shared
intake lifecycle router and explicitly closes the original item — never
silently dropping it.

This realizes SPECIFICATION/scenarios.md "Scenario 7 — Regroom an
oversized work-item" and the contracts.md §"Gap-detectable behavior
clauses" groom clause. The mechanical seam is
`livespec_orchestrator_beads_fabro.commands.groom`; the load-bearing state transition
reuses the shared `livespec_orchestrator_beads_fabro.regroom` backlog
disposition helpers, and slice filing reuses the `capture-work-item`
operation's store + intake-routing machinery — `groom` adds NO new ledger
state and no new store path.

## Pre-requisites

- The target work-item id is at `backlog` status (this operation refuses
  any other target).
- The `livespec-orchestrator-beads-fabro` Python package is on the import path.
- `livespec` installed (a spec-change slice routes to the
  `propose-change` operation).

## Flow

### Step 1 — Load the read-only grooming context

Confirm the target is actually at `backlog` and read it WITHOUT
mutating anything. `load_groom_context` raises if the id is absent
(`WorkItemNotFoundError`) or not at `backlog`
(`GroomTargetNotBacklogError`) — surface either to the user and stop.

```python
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands.groom import load_groom_context
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
context = load_groom_context(path=config, item_id=item_id)
# context.title / context.description ground the draft in the real item.
```

Then read (read-only) the relevant spec / scenarios and the ledger (via
the `list-work-items` operation, `--json`) for surrounding context.

### Step 2 — Draft the layered decomposition (READ-ONLY)

Draft candidate slices. Each candidate is pre-filled with all of:

- **acceptance** — exactly one coherent, autonomously-verifiable "done"
  (a named scenario, or the standing `just check` + `/livespec:doctor`
  gates).
- **autonomy tier** — `factory` (autonomously dispatchable) or
  `human-gated` (a spec change). A spec-change slice is marked
  `is_spec_change=True` and routes to the `propose-change` operation,
  NOT the factory.
- **dependency links** — the draft-local TITLE of any EARLIER factory
  slice this one is blocked by (the dependency-layer arrangement).
  Arrange the draft so blockers precede the slices they block.
- **repo target** — the one ledger the slice lands in.
- **scope** — the slice body.

When the draft discovers required workflow-file wiring, split that wiring
into an explicitly maintainer-side step: factory slices never create or update
files under `.github/workflows/`, so the factory slice carries the product
change and reports the workflow diff for maintainer-side landing.

Present the draft to the maintainer. The maintainer OWNS the cut and the
acceptance — `groom` only proposes. The draft is READ-ONLY: nothing is
filed until the maintainer approves. The maintainer may edit the cut /
acceptance / deps / tiers and approve, or send it back to re-draft.

Capture the approval as a RECORD, not as a remembered fact. When the
approval arrives, note WHO approved (the approving invoker's identity) and
HOW the approval was obtained (the route it arrived on — under the
two-phase groom variant, the `resolve-blocked:<work-item-id>:ready` valve
plus the ledger comment the answer landed as). Step 3 requires both, refuses
to file without them, and stamps them where a later reader can query them.
Do NOT synthesize either value: an identity you invented attributes the cut
to someone who never approved it, which is worse than the refusal.

### Step 3 — On approval, file the slices and regroom the original out

ONLY after explicit approval, file the approved factory slices and
explicitly dispose the original backlog item. The approval is passed as a
required `GroomApproval` record — the mechanism that makes "only after
approval" an enforced precondition of this seam rather than an obligation on
this prose's reader:

```python
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    GroomApproval,
    file_approved_slices,
)

result = file_approved_slices(
    path=config,
    regroom_item_id=item_id,
    approval=GroomApproval(
        approver=...,   # WHO approved — the approving invoker's identity.
        route=...,      # HOW it was obtained — e.g. the resolve-blocked
                        # valve plus the ledger comment carrying the answer.
    ),
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
# result.filed_slice_ids        — factory slices filed through intake routing, deps linked.
# result.criteria_parses        — each filed slice's effective-criteria parse (display it).
# result.spec_change_slices     — the human-gated slices to route (Step 4).
# result.regroomed_out is True  — the original backlog item was closed explicitly.

criteria_advice = [
    f"{parse.slice_id}: {parse.criteria.parse_display()}"
    for parse in result.criteria_parses
]
```

Show the user every line of `criteria_advice`. This is ADVICE, never a
refusal: an empty parse at groom time is legitimate — criteria may arrive at
approve time — but the maintainer must SEE it, because an AI-dispositive slice
whose effective acceptance criteria parse to zero gradeable assertions is later
refused entry to `ready` and refused at dispatch
(`SPECIFICATION/contracts.md` §"Effective acceptance criteria").

`file_approved_slices` files each factory slice via the same
`append_work_item` machinery the `capture-work-item` operation uses, then
routes each local slice through the shared intake Definition-of-Ready router.
If the draft files NO local factory slice (an all-spec-change cut), groom
REFUSES (`GroomExitRefusedError`) and the original STAYS `backlog` —
escalate-don't-drop. A `depends_on` handle naming no earlier factory
slice is a malformed cut (`GroomDraftError`); surface it and re-draft.
The whole cut is resolved BEFORE the first slice is filed, so that refusal
leaves the ledger untouched and the corrected draft simply re-runs. Note
what the handle rule implies: a spec-change slice routes to
`propose-change` and is never minted, so a factory slice CANNOT name one
as a blocker even though it may genuinely be blocked by it. Draft that
ordering constraint as prose in the dependent slice's description and
route the spec change first.

An absent `approval`, or one naming no approver identity or no route, is
refused with `GroomApprovalRequiredError` BEFORE any slice is filed, so a
refusal leaves nothing half-filed and the original at `backlog`. On a
successful filing the record is stamped on every filed slice AND on the
regroomed-out original, in the queryable `groom_approval` metadata field —
`groom_approval_for(path=config, work_item_id=...)` reads it back. That
stamp is the forensic difference between a cut the maintainer approved and
one approved by a peer or by the agent itself; without it the ledger cannot
tell the three apart after the fact.

### Step 4 — Route the spec-change slices to the propose-change operation

For each entry in `result.spec_change_slices`, invoke the cross-boundary
handoff to the `propose-change` operation — these NEVER reach the
factory:

```text
the propose-change operation --spec-target SPECIFICATION/ \
    --topic <slug> --body "<slice scope + acceptance>"
```

### Step 5 — Summary

Report: the original item id (now explicitly regroomed-out), the filed
slice ids with their routed lifecycle statuses and dependency layers, and the
spec-change slices routed to the `propose-change` operation. The Dispatcher
then drains eligible factory slices by dependency layer.

## Important properties

- **Read-only until approval** — `load_groom_context` and the drafting
  conversation mutate NOTHING; only `file_approved_slices` (post-approval)
  writes, and it refuses to write at all without an approval record.
- **Approval is recorded, not assumed** — the approver identity and the
  route the approval arrived on are stamped on every filed slice and on the
  regroomed-out original, so who approved a cut stays answerable later.
- **Escalate-don't-drop** — the original backlog item is closed ONLY
  after real local factory slices are filed; an all-spec-change cut leaves it
  `backlog`.
- **No new ledger state, no new store path** — reuses the shared
  `regroom` helpers and the `capture-work-item` operation's store + intake
  routing path.
- **Spec-change slices route to the `propose-change` operation** — never
  the factory.

## What this operation does NOT do

- Does NOT file anything before the maintainer approves the draft.
- Does NOT delete the original item — it closes it with an explicit
  regroomed-out disposition after replacements are filed.
- Does NOT dispatch slices — the Dispatcher drains the factory slices.
- Does NOT detect gaps or drift. Use the `capture-impl-gaps` /
  `capture-spec-drift` operations.
