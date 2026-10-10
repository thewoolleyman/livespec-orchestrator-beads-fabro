# discuss-work-item

Per `SPECIFICATION/constraints.md` §"Skill orchestration constraints", this is the harness-neutral operation prose; each runtime binding only maps its tools to it.

## What done looks like

This operation stands by: it answers, drafts, and records while retaining the explicit-instruction
gate on every lifecycle drive.

`discuss-work-item` is the maintainer's day-to-day session over one work item or plan, layered over
the `context` read primitive. The sibling `plan` operation owns create, resume, and archive.

## Pre-requisites

- The `livespec-orchestrator-beads-fabro` Python package is on the import
  path; the bundled wrappers self-bootstrap it.
- A reachable work-items store exists, holding the subject work item or the
  plan epic the subject slug anchors.
- The `context` operation is available as this plugin's read primitive.
- `livespec` is installed for the cross-boundary `propose-change` and
  `doctor` operations.

## Package Commands

The operation reads through this plugin's own `context` wrapper and writes
through the Planning Lane primitives in
`livespec_orchestrator_beads_fabro.commands.plan`:

- `context <plan_slug | work_item_id> --json` assembles the whole context
  envelope in one query-only call: the resolved `subject` record, its `epic`,
  `comments`, `children`, `dependencies`, the plan's typed `next_action`, the
  `research` directory its anchor resolves, and the `spec` clauses it and its
  children cite.
- `record_scope_event(...)` records a maintainer ruling as a plan scope event
  on the plan epic — the requirement carriers it admits and the deferrals it
  makes explicit.
- `read_timeline(...)` reads the plan's handoff and scope comments
  oldest-first, each labelled with its `kind`, and is how a scope-event write
  is read back before it is reported as recorded.
- `append_handoff(...)` and `set_next_action(...)` move the plan's typed
  `next_action` when a ruling changes what happens next.

Use `list-work-items` and `next` for their existing read-only status
responsibilities, `capture-work-item` to file ripe work, and `drive` to
execute one lifecycle action id.

## Flow

### Step 1 - Resolve The Subject

The operation takes exactly one required argument: a `plan_slug` or a
`work_item_id`. There is no interactive-entry mode and no bare invocation —
this operation opens ON something. If the argument is absent, ask for it
rather than guessing a subject from the session's history.

### Step 2 - Assemble The Context Envelope

Assemble the subject's context by invoking the `context` primitive with
`--json`. Do NOT hand-roll a per-item read: a hand-rolled read is how a child
enumeration silently drops one of the two linkages, and how a `parent-child`
edge gets counted as a blocker. Every assembly rule that makes the envelope
correct lives in the primitive, and re-deriving it here would produce a second
reading that diverges without announcing it.

`context` exits 3 naming the missing key when the subject does not resolve.
Surface that refusal verbatim and stop; it is never an invitation to retry
with a guessed id, and the primitive deliberately does not emit an empty
envelope, because an empty envelope is indistinguishable from a plan that has
not started.

### Step 3 - Resume From The Envelope Alone

The envelope is the WHOLE read. A session opening this operation has no chat
history and MUST NOT need any: recover the plan's current facts from the
envelope's `epic`, `comments` and `children`, and recover what happens next
from its typed `next_action` — the `kind`, the `ref`, and the one imperative
sentence in `text`. Read `research` for the reasoning already captured, and
`spec` for the clauses the subject and its children cite.

A prose "next action" line inside a handoff comment body carries no authority.
When it disagrees with the typed `next_action`, the typed field wins: a
wrapped prose line has twice truncated the instruction on a live tenant, once
deleting a constraint and once the factory route, while the resume reported
one confident action.

Open the session by stating what the envelope says — the subject, its status,
its blockers, and its recorded next action — so the maintainer can correct a
stale pointer before anything acts on it.

### Step 4 - Stand By

The resting state is standing by. In this state the operation:

- Answers questions about the subject from the envelope, naming which field
  each answer came from. When the envelope does not carry the answer, say so
  and offer to widen the read rather than inferring one.
- Drafts research. A research note is written under the plan's
  `plan/<slug>/research/` directory, and is offered to the maintainer before
  it is written.
- Records rulings. See Step 5.
- Offers plan scaffolding that needs no operation of its own — creating the
  plan epic, the research directory, the write-once `associated_work_item_id`
  anchor file, or the archive move. Offer these when the envelope shows one
  missing; `doctor` is the surface that REPORTS what is missing, so route a
  maintainer asking "what is not set up here?" to `/livespec:doctor` rather
  than re-implementing its invariants.

Standing by is not passivity: surface what looks wrong, name the decision the
maintainer is being asked for, and propose the action you would take. What
standing by forbids is TAKING that action unasked.

### Step 5 - Record A Maintainer Ruling As A Scope Event

When the maintainer states a ruling — what is in scope, what is explicitly
deferred, which option was chosen — record it as a plan scope event through
`record_scope_event(...)` on the plan epic. Do not leave a ruling in chat: a
ruling that lives only in the session is lost at the next resume, and Step 3's
envelope-alone guarantee is exactly the guarantee it breaks.

The write is a store write performed on the maintainer's behalf, so it is
consented before it executes, per `SPECIFICATION/contracts.md` (the
store-write consent discipline). Present the drafted requirements and
deferrals, obtain consent, then write.

Deferrals must be concrete: what is deferred, why it is not part of the
current implementation children, and where it will be reconsidered. Read the
event back through `read_timeline(...)` before reporting it as recorded — a
ledger comment is not verified by the call returning.

### Step 6 - Drive Only On Explicit Instruction

A lifecycle action — dispatching implementation, approving, accepting,
rejecting, editing an admission or acceptance policy, archiving — executes
ONLY on an explicit maintainer instruction to take it. Execute it through
`drive` with the action id, never by reaching around that operation into the
store.

An implicit or ambiguous request MUST NOT trigger a drive. "This looks ready",
"we should probably ship it", and a question about whether an item COULD be
dispatched are not instructions; neither is a next action recorded on the
epic, which is a pointer rather than a mandate. In every such case, stand by:
state the action you believe is being asked for, name its consequence, and ask
for explicit confirmation. Ask one question at a time.

The asymmetry is deliberate. Standing by when the maintainer meant "go" costs
one turn; driving when they did not costs a dispatch, a factory slot, and a
merged branch nobody asked for.

## Important Properties

- The subject's context is assembled through the `context` primitive, never
  through a hand-rolled per-item read.
- The operation resumes from the context envelope alone, with no chat history.
- A maintainer ruling becomes a durable plan scope event, consented before the
  write and read back after it.
- Driving is explicit-instruction-only; ambiguity resolves to standing by and
  asking, never to acting.
- The operation is registered as `discuss-work-item`, never as `plan`.
- Plan scaffolding may be offered here; reporting what is missing belongs to
  `doctor`.

## What This Operation Does Not Do

- Does not hand-roll an item read that `context` already assembles.
- Does not drive a lifecycle action on an implicit or ambiguous request.
- Does not write to the store without per-operation maintainer consent.
- Does not leave a maintainer ruling recorded only in the session.
- Does not implement child work inline; ripe work is filed through
  `capture-work-item` and dispatched through `drive`.
- Does not duplicate `doctor`'s invariant reporting.
