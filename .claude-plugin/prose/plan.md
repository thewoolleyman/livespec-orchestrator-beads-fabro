# plan

Harness-neutral driving prose for the `plan` operation, per
`SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the planning-thread create/resume dialogue, the reasoning-capture and
handoff-refresh writes, the matured-piece routing, the handoff
self-sufficiency gate, and the archive-on-close transition. Each
per-runtime SKILL.md is a THIN binding that resolves the plugin root,
reads this prose in full, and maps its harness-neutral vocabulary (the
`<plugin-root>` token, the "ask the user" / "read the file" / "write
the file" / "fresh-context reader" verbs, the named sibling operations)
to that runtime's tools. Nothing in this file names a specific agent
runtime's tools or command namespace.

`plan` is the Orchestrator-Plane realization of the **Planning Lane** —
the durable, multi-session *planning* work that decides what should
become spec, implementation, or research before any of those lanes is
committed to. It realizes the repo-agnostic pattern that
`livespec`'s `non-functional-requirements.md` §"Planning Lane guidance"
carries (the same cut as grooming: core records the pattern, this
plugin realizes it), and the contract for this realization is
`SPECIFICATION/contracts.md` §"Planning Lane realization". Unlike the
one-shot `capture-*` family, a planning thread is **stateful and
re-entered** for the same topic, like `groom`.

## Pre-requisites

- The `livespec-orchestrator-beads-fabro` Python package is on the
  import path (the wrappers self-bootstrap it).
- A reachable work-items store (a planning thread anchors a ledger
  epic and routes ripe work into the ledger).
- `livespec` installed (a matured-reasoning piece routes to the
  `propose-change` operation).
- A `plan/` directory at the project root is the thread store; the
  operation creates it on first use.

## The planning-thread store

A planning thread is a first-class directory **`plan/<topic>/`** holding
two facets:

- **At most one handoff** — the reserved filename
  `plan/<topic>/handoff.md`, the single resumable execution-coordination
  point for the thread. Only one resumption point may be active per
  topic; a second handoff (any other `handoff*.md`) is malformed and
  this operation refuses to create it.
- **Zero or more research files** — durable reasoning ("why this
  shape"). A single note MAY sit directly in `plan/<topic>/`; multiple
  sub-topic notes live under `plan/<topic>/research/` (the directory
  carries the topic, so the filenames do not repeat it). A young thread
  MAY be research-only (no handoff yet).

There is NO root `research/` tree: standalone analysis lives in a plan
thread (or, once the thread closes, under `plan/archive/`), and a
living reference document lives in `docs/`, `.ai/`, or a dedicated
top-level topic directory (precedent: `loop-reflection-gate/`).
Archived threads live under `plan/archive/<topic>/`.

## Flow

### Step 1 — Resolve the invocation mode

This operation has two entry modes, fixed by whether a `<slug>`
argument was supplied:

- **No argument → interactive entry** (Step 2). Used to resume an open
  thread or start a new one.
- **`<slug>` argument → strict resume** (Step 3, against an existing
  thread only). Deterministic: it MUST match an existing `plan/<slug>/`
  exactly. If no such directory exists, FAIL HARD with an error that
  lists the existing slugs (the open threads). There is NO fuzzy match
  and NO accidental create-on-typo — creation happens only through the
  no-argument interview path (Step 2).

### Step 2 — Interactive entry (no argument): resume or create

Compose the open-thread list from BOTH sources and present it:

1. The ledger's open planning epics — via the `list-work-items`
   operation (`--json`), the ledger ids whose thread the human may
   resume. Status is READ from the ledger here; it is never stored in a
   planning artifact (the no-shadow-ledger rule).
2. The on-disk threads — the `plan/<topic>/` directories (excluding
   `plan/archive/`).

Ask the user whether to **resume** one of the listed threads (→ Step 3
against that slug) or **start a new** thread.

To start a new thread, ask the user to describe it in one or two
sentences, then **propose a canonical dash-cased slug** derived from
that description using the SAME canonicalization the `propose-change`
operation applies to a topic hint: lowercase → replace every run of
non-`[a-z0-9]` characters with a single hyphen → strip leading and
trailing hyphens → truncate to 64 characters. The human never
hand-crafts the identifier, so there are no spaces, no over-long
strings, and the output is deterministic. Confirm the proposed slug
with the user (offer to adjust the description if the slug reads
poorly), then on confirmation:

- **Create the thread directory** `plan/<slug>/` (write the initial
  reasoning note the user described, or leave it for a later
  invocation).
- **Anchor a ledger epic** for the thread via the `capture-work-item`
  operation — an `epic`-type work-item whose title names the thread.
  This is the thread's status anchor; its id is what the handoff and
  the open-thread list cite. Filing through `capture-work-item` keeps
  the cross-plane write per-operation consented and routes it through
  the one consented store-writer (never a direct cross-plane write).

### Step 3 — Work the thread

Within a thread (resumed by slug or just created), any of the following
may happen this invocation; ask the user which, one at a time:

- **Update the reasoning.** Write or revise a research note under
  `plan/<slug>/` (or `plan/<slug>/research/` for a sub-topic).
- **Refresh the handoff.** Write or update `plan/<slug>/handoff.md`,
  then run the **handoff self-sufficiency gate** (Step 4) before
  declaring it ready. A handoff cites the thread's ledger ids
  read-only and composes status from `list-work-items` / `next`; it
  never embeds a parallel `[ ]`/`[x]` work queue that shadows the
  ledger.
- **Route a matured piece.** When a piece of the thread is ripe:
  - *becomes spec* → hand off to the `propose-change` operation
    (cross-boundary, human-accepts).
  - *becomes ledger work* → file it via the `capture-work-item`
    operation as a CHILD of the thread's epic anchor (linked via
    `depends_on`). Routing ripe work into the ledger is
    the second of the two one-directional seams; it always goes through
    `capture-work-item`, never a direct store write. The planning
    session **FILES** ripe work; it does **NOT** hand-code the
    implementation inline. Ready, factory-safe implementation is built
    **factory-side** under the janitor gate — the Dispatcher drains
    `ready` items, or an operator runs the `drive` operation —
    never inline in the planning session (that is the retired
    inline-overseer anti-pattern).
- **Close the thread** → archive it (Step 5).

### Step 4 — The handoff self-sufficiency gate

A handoff is NOT ready until it is self-sufficient: a fresh session
opening ONLY the handoff can execute its next action without
re-deriving anything. Enforce all four before declaring a handoff
ready; if any fails, repair the handoff and re-run the gate.

1. **Cold-open readiness test.** Have a **fresh-context reader** (a
   sub-agent with no prior session context in runtimes that provide
   one; otherwise a deliberately cleared re-read) open ONLY the handoff
   and the artifacts on its read-first chain, and confirm it can
   proceed to the named next action without consulting chat history or
   re-deriving anything. If the reader cannot proceed, the handoff is
   not self-sufficient — fix it (commit the missing artifact, add it to
   the read-first chain) rather than relying on conversational context.
2. **One path.** The next-session command names exactly ONE path — the
   handoff. If the handoff's "next" text needs to ALSO list other
   files, that is the smell that the handoff is not self-sufficient:
   fold those references into the handoff's read-first chain and fix the
   handoff, do not list more paths.
3. **No dangling reference (fail-closed).** Every artifact the handoff
   cites — its read-first chain and its next action — MUST exist and be
   committed. Check each referenced path with the runtime's shell
   (`git ls-files --error-unmatch <path>`, or existence + tracked
   status); a missing or uncommitted reference FAILS the gate. Surface
   the offending path and stop — do not declare the handoff ready.
4. **Dispatch routing (the factory path).** When the handoff's next
   action includes implementing ledger-backed work, it MUST name the
   factory dispatch route — the `drive` operation (action `impl:<id>`)
   or the Dispatcher drain — as THE implementation path, and it MUST
   NOT direct the reader to the in-session Red→Green driver (the
   `implement` operation), except for items explicitly recorded as
   factory-ineligible. "Factory path" refers EXCLUSIVELY to dispatch
   through the Dispatcher/`drive`; a handoff that uses the phrase for
   in-session implementation FAILS this gate.

### Step 5 — Archive on epic close

A plan thread's lifecycle binds to its ledger epic: `plan/<topic>/` is
active if and only if its epic is open, and archived to
`plan/archive/<topic>/` if and only if the epic is closed. When the
user closes the thread, close the epic anchor (via the ledger) AND move
the directory:

```text
git mv plan/<topic>/ plan/archive/<topic>/
```

Reopening the epic unarchives it (move back). Nothing is lost — the
archived thread stays under `plan/archive/` and in git history; to keep
a research note as living reference, move it to `docs/`, `.ai/`, or a
dedicated top-level topic directory deliberately. In spirit this is
`prune-history` for planning threads:
the active view stays clean, completed threads move aside rather than
getting deleted.

The mechanical backstops (exactly one handoff per topic; `archived`
matches `epic-closed`) are five-slot conformance concerns whose
always-on enforcement is realized by the Conformance Pattern, not by
this operation; this prose enforces them behaviorally (it writes only
the reserved `handoff.md`, and it archives on close).

## Important properties

- **Status is derived, never stored** — the open-thread list and every
  handoff compose status from the ledger (`list-work-items` / `next`)
  as a read-only first action; no planning artifact stores a status or
  a shadow work queue (the no-shadow-ledger rule).
- **Two one-directional seams** — *prompt → ledger* is read-only (cite
  ids, compose status); *plan → work* routes ripe work through the
  `capture-work-item` operation. Never a direct cross-plane store
  write.
- **Strict `plan <slug>`** — the argument form never creates; it
  resolves an existing thread or fails listing slugs. Creation is the
  interview path's job, with a canonical slug the human confirms.
- **Self-sufficient handoffs** — a handoff is declared ready only after
  the Step 4 gate (cold-open test + one path + no dangling reference +
  dispatch routing).
- **No new ledger state, no new store path beyond `plan/`** — the
  thread anchors a plain Beads `epic` and reuses the `capture-work-item`
  machinery; `plan/<topic>/` and `plan/archive/<topic>/` are the only
  new paths.

## What this operation does NOT do

- Does NOT write the ledger directly — epic anchors and child work-items
  are filed through the `capture-work-item` operation; status is read
  through `list-work-items` / `next`.
- Does NOT create a thread from the `<slug>` argument form — that form
  is strict-resume-or-fail.
- Does NOT decompose an epic into ready slices — use the `groom`
  operation.
- Does NOT detect gaps or drift — use the `capture-impl-gaps` /
  `capture-spec-drift` operations.
- Does NOT dispatch work — the Dispatcher drains `ready` items.
- Does NOT implement work inline — a planning session FILES ripe work
  and never hand-codes its implementation; ready, factory-safe
  implementation is built factory-side (the Dispatcher / `drive`)
  under the janitor gate.
