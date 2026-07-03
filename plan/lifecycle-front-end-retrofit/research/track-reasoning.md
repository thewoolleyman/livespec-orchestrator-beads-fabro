# lifecycle-front-end-retrofit — why this shape

Opened 2026-07-03 from the overseer kickoff brief
(`tmp/overseer/kickoff-lifecycle-front-end-retrofit.md`, untracked). The
maintainer approved all three workstreams — including the Workstream A
epic cut — up-front through the overseer session on 2026-07-03; those
decisions are not re-gated here.

## The problem

The work-item lifecycle state machine is RATIFIED in the spec
(`SPECIFICATION/contracts.md` v020–v026: 7 states
`backlog · pending-approval · ready · active · acceptance · blocked · done`)
and implemented in the store/dispatcher/next/doctor layers (L1a epic
`bd-ib-vvrxcb`, closed; released v0.3.0). But the maintainer-facing
FRONT-ENDS were never retrofitted — they still implement the retired
label-based triage. Verified against master `66beddf` (2026-07-03):

- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/intake_dor.py`
  stamps beads LABELS (`ready` / `needs-regroom` / `not-yet-actionable`)
  instead of routing items into lifecycle STATES; its module docstring
  quotes a superseded pre-v020 contract clause.
- `.../regroom.py` is the retired `needs-regroom` LABEL state machine
  (contracts.md §"Resolved realization choices" ratifies there is NO
  needs-regroom label or status).
- `.../commands/groom.py` + `.claude-plugin/prose/groom.md` gate on the
  needs-regroom label and file slices at `status="ready"` directly; the
  ratified contract (§"Grooming and slice-size calibration", Scenario 9)
  targets `backlog`-STATUS items.
- `.../commands/_orchestrator_gap_capture.py:152` hardcodes
  `status="backlog"` on every filed gap item instead of running the
  intake Definition-of-Ready routing (contracts.md §"Gap-detectable
  behavior clauses", ~line 824).
- `.../commands/orchestrate.py` handles only `impl:` / `spec:` action
  ids; the contracted human-valve actions `approve:<id>` / `accept:<id>`
  / `reject:<id>:rework|regroom` (contracts.md §"`orchestrate`" →
  "Human valve actions", Scenario 31) are unimplemented. The store seam
  they need (`store.update_work_item_status`, `store.py:290`) exists.

Related-but-narrower: `bd-ib-syb` (CLOSED via `ec5a598`) fixed one stale
`status="open"` constructor example in `capture-work-item.md` prose. The
A1 slice links to it and does not duplicate it.

## The approved cut (Workstream A)

One epic + three slices, filed 2026-07-03 through the consented
`capture-work-item` store seam (`append_work_item`):

- **`bd-ib-ew7bdv`** — the epic anchor for this thread.
- **`bd-ib-r3vsnd` (A1)** — intake Definition-of-Ready lifecycle-state routing; retire
  label stamps; fix the hardcoded gap-capture status.
- **`bd-ib-h2tnil` (A2)** — groom re-expression to backlog-STATUS
  targeting; retire the needs-regroom label machinery. `blocks`-edge
  dependency on A1.
- **`bd-ib-q3x6va` (A3)** — orchestrate human-valve actions
  (`approve:` / `accept:` / `reject:`). Independent of A1/A2.

Slices are dispatched through the factory SEQUENTIALLY (A1 → A2; A3 at
any point), never hand-coded inline in the planning session.

## Filing-time decisions (recorded for audit)

- **Parent-child linkage** via `bd dep add <child> <epic> --type
  parent-child`, matching the L1a precedent (`bd-ib-7mounw` →
  `bd-ib-vvrxcb`); slice ordering via a typed local `depends_on`
  (`{"kind": "local", "work_item_id": ...}`) → `blocks` edge.
- **`admission_policy: auto` + `acceptance_policy: ai-only`** on the
  three slices: the maintainer pre-approved dispatching all three, and
  their acceptance is autonomously verifiable (tests + `just check` +
  the red-green-replay protocol), so no human acceptance valve is
  required per-slice. The epic carries no policy overrides.
- **Intake Definition-of-Ready label stamps**: applied to the three slices (verdict
  `ready` — all six gates genuinely pass; A2's blocker is LINKED, which
  is what the gate asks). Deliberately NOT applied to the epic: the
  honest verdict for an epic is the `needs-regroom` LABEL, but that
  label machinery is retired by the ratified contract and this very
  epic's A2 slice deletes it; the epic is already groomed (the approved
  cut IS its decomposition), so stamping it would misrepresent state and
  feed the retired workflow. This inconsistency dissolves when A1 lands.
- **Interim dispatchability mechanism**: today's `next`/dispatch path
  ranks `ready`-STATUS items only, and the valve surfaces (A3) that
  would normally perform admissions do not exist yet. Per the kickoff
  brief this track sets slice statuses through the store seam /
  `bd update` as the SANCTIONED INTERIM mechanism (each flip journaled
  in the work-item `notes` and this thread).

## Workstream B — the pending-approval → ready ownership hole

The ratified contract leaves a `manual`-admission item's
`pending-approval → ready` transition with no owner: capture
auto-approves only `auto`-policy items into `ready`; the `approve:`
valve action acts on items already AT `ready`; the v023 critique's
approval-model finding was resolved toward valve-side admission but the
conditional "approved on into `ready` when … `auto`" routing language
survived. Filed as a proposed change (see
`SPECIFICATION/proposed_changes/`) recommending: `pending-approval →
ready` is the structural grooming gate only — an item that passes the Definition-of-Ready checklist
proceeds to `ready` regardless of admission policy, and ALL human
permission is exercised at the admission valve (matches Scenario 23/31
and "the human's explicit admission IS the approval act").
Ratification via `/livespec:revise` is a maintainer gate — the proposal
is filed, not self-revised.

## Workstream C — backlog re-triage

Draft disposition table (read-only until maintainer approval):
`research/backlog-retriage-draft.md` in this thread.
