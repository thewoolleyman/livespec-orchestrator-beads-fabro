# plan

Harness-neutral driving prose for the `plan` operation, per
`SPECIFICATION/constraints.md` "Skill orchestration constraints".
This artifact is the plugin-owned LLM-facing half of the Planning Lane:
the thread create/resume dialogue, write-once research capture, the
ledger epic anchor, ledger-held handoff timeline entries, scoping
events, routed child work, and archive gates. Each per-runtime
`SKILL.md` is a thin binding that resolves the plugin root, reads this
prose in full, and maps the neutral verbs below to that runtime's tools.

`plan` is stateful and re-entered for the same topic. It decides what
should become spec, implementation, or research before those lanes are
committed to. The durable coordination record is the plan epic in the
beads ledger; filesystem artifacts hold research only.

## Pre-requisites

- The `livespec-orchestrator-beads-fabro` Python package is on the
  import path; the bundled wrappers self-bootstrap it.
- A reachable work-items store exists. A plan anchors exactly
  one ledger `epic`.
- `livespec` is installed for the cross-boundary `propose-change`
  operation.
- A `plan/` directory at the project root is the plan store; the
  operation creates it on first use.

## The Plan Store

A live plan has two stores:

- Filesystem research under `plan/<topic>/research/`. Creation writes
  one initial research note and no other filesystem artifact. Further
  reasoning updates add or revise research notes deliberately.
- One write-once plan epic in the beads ledger. The epic carries the
  thread slug in its metadata and is the status anchor, handoff anchor,
  scope-event anchor, and archive lifecycle anchor.

The operation never authors `plan/<topic>/handoff.md`. Handoffs are
append-only comments on the plan epic. Each entry is one ledger comment,
attributed and timestamped, and is read through the same timeline read
path used by the package command. Existing legacy `handoff.md` files may
be read only as historical migration input; do not create or update one.

Archived threads move whole directories to `plan/archive/<topic>/`.
There is no root `research/` tree: standalone analysis lives in a plan
thread, or after closure under `plan/archive/`.

## Package Commands

The operation's testable package substrate is
`livespec_orchestrator_beads_fabro.commands.plan`:

- `create_thread(...)` creates `plan/<slug>/research/<file>` and one
  ledger epic anchor. Its `definition_of_done` is a REQUIRED
  `PlanDefinitionOfDone(statement=..., assertions=...)`. See "The plan
  Definition of Done" below.
- `append_handoff(...)` appends one plan-epic comment, with a
  caller-supplied `author`, and writes the required `next_action` onto the
  epic in the same call. See "The typed next action" below.
- `append_supervisor_handoff(...)` appends one plan-epic comment on
  behalf of the plan's supervisor role, computing the reserved
  `<slug>-supervisor` author literal internally (never caller-supplied).
  A supervisor session driving this operation MUST use this call, never
  `append_handoff`, for its own handoff entries.
- `set_next_action(...)` updates the epic's `next_action` and
  `last_session` metadata in place, without appending a comment. Use it
  when the pointer changes and there is nothing new to narrate.
- `read_timeline(...)` reads plan handoff and scope comments
  oldest-first, each labelled with its `kind` (`handoff` or `scope`).
- `is_unattended_session(...)` reports whether this session carries the
  unattended marker, and `resume_directive(...)` reads the epic's typed
  `next_action` and decides whether this resume asks which action to take
  or takes it. See Step 3's "Unattended resume".
- `record_scope_event(...)` records requirement carriers and explicit
  deferrals before implementation children are admitted. Pass `carriers`
  to make it a carrier-map event; omit it for a ruling. See "The carrier
  map" below.
- `close_plan_child(...)` and `reparent_plan_child(...)` dispose one plan
  child with a recorded rationale. See Step 3's "Child disposition".
- `plan_record_rate_warnings(...)` reports the days on which this thread's
  record authoring ran past a threshold. See Step 3's "Record rate".
- `record_completeness_review_evidence(...)` appends one durable
  independent completeness-review evidence comment to the plan epic. It
  takes NO reviewer identity: the record's `reviewer-identity` is
  COMPUTED from the invoking session — its agent-session id, or the forge
  login for a human at a terminal — exactly as the Proof-of-Done posting
  primitives compute theirs. The REVIEWER must therefore make this call
  itself, from its own session. A call the archiving session makes on a
  reviewer's behalf records the ARCHIVER as the reviewer, and the archive
  then refuses that evidence as a self-review.

  It DOES take `reviewed_child_ids`, and that argument is required: it is
  the set of child work-item ids the review actually read, which the
  archive compares against the epic's child set at archive time. Pass the
  `child_ids` of the `ArchiveCompletenessReviewRequest` the review was
  commissioned with — that is the same set the archive grades against,
  read once. A record naming a different set, or one written before a
  current child's latest status change, is reported as STALE rather than
  accepted.
- `archive_thread(...)` performs the child-disposition gate, sweeps the
  working tree outside `plan/` for files that read `plan/<slug>/` by
  path, computes the archiving party's own identity, launches a supplied
  fresh independent reviewer when valid review evidence is absent,
  re-reads the ledger for durable evidence, and moves the thread
  directory to `plan/archive/<slug>/` only after every gate passes.
- `outside_plan_path_references(...)` is that sweep on its own, for a
  session that wants the hit list before it attempts the archive.

Use those package calls when this operation needs deterministic local
behavior. Continue to use `list-work-items`, `next`, and
`capture-work-item` for their existing public skill responsibilities.

## Flow

### Step 1 - Resolve The Invocation Mode

This operation has two entry modes:

- No argument means interactive entry. Resume an open thread or start a
  new one.
- A `<slug>` argument means strict resume. It must match an existing
  live `plan/<slug>/` exactly. If it does not, fail hard and list the
  existing live slugs. Do not create on a typo.

### Step 2 - Interactive Entry

Compose the open-thread list from both sources and present it:

1. Open planning epics from the ledger via `list-work-items --json`.
   Status is read from the ledger only; it is never copied into a
   planning artifact.
2. Live filesystem threads from direct child directories under `plan/`,
   excluding `plan/archive/`.

Ask whether to resume one listed thread or start a new thread.

To start a new thread, ask for a one- or two-sentence topic
description. Propose a canonical dash-cased slug using the same
canonicalization as `propose-change`: lowercase, replace each run of
non-`[a-z0-9]` characters with one hyphen, strip leading and trailing
hyphens, and truncate to 64 characters. Confirm the proposed slug.

Before creating anything, ask the maintainer what DONE means for this
plan, in their own words, and derive the plan's Definition of Done from
their answer. See "The plan Definition of Done" below; `create_thread`
requires it.

On confirmation, create exactly these records:

1. One initial research note under `plan/<slug>/research/`.
2. One ledger `epic` anchor for the thread, carrying `plan_slug`.
3. The write-once file `plan/<slug>/associated_work_item_id`, holding
   that epic's id on one line. `create_thread` writes all three; when the
   slug names a directory of standalone research whose anchor still reads
   `unassigned`, the epic ADOPTS it and the anchor is completed to the
   epic id rather than rewritten from one id to another.

Do not create `handoff.md`, status files, terminal markers, local queue
files, or any other thread metadata file.

### Step 3 - Work The Thread

Within a thread, perform one action at a time. Which action comes from
`resume_directive(...)`: an attended resume asks, and an unattended one
whose epic carries a dispatchable typed next action takes it. See
"Unattended resume" below.

- Update reasoning. Add or revise a research note under
  `plan/<slug>/research/`.
- Append a handoff entry. Write one plan-epic ledger comment with the
  current facts and read-first chain, and supply the `next_action` the
  same call writes onto the epic. Read it back through
  `read_timeline(...)` before declaring it recorded.
- Record a scoping event. Before implementation children are admitted,
  write a scope comment that names the requirement carriers and the
  explicit deferrals. Deferrals must be concrete: what is deferred, why
  it is not part of the current implementation children, and where it
  will be reconsidered.
- Route a matured piece. If it becomes spec, hand it to
  `propose-change`. If it becomes ledger work, file it through
  `capture-work-item` as a child of the plan epic after the scoping
  event exists. Planning sessions file ripe work; they do not implement
  it inline. Authoring the child's Definition of Done is part of routing it
  — see "Routing a child's Definition of Done" below.
- Dispose a child. Close or re-parent a plan child that no longer belongs
  under this epic. See "Child disposition" below.
- Close the thread. Run the archive gates in Step 5.

#### Routing a child's Definition of Done

An implementation child is implement-kind, so it carries a
`## Definition of Done` section as the FIRST heading of its description, and
this front-end owes the same authoring rules the capture and groom front-ends
owe when they file one. They are the rules the `dod_gate` node and the
host-side wall both grade the child against
(`SPECIFICATION/contracts.md` §"Definition of Done and Proof of Done").

- **One behavioural assertion per bullet.** Each `- ` bullet is ONE
  gradeable assertion naming an observable behaviour of the delivered
  artifact on a real surface, written as a complete sentence ending in a
  period. An assertion whose subject is the existence, coverage or passing
  of tests or checks is a TEST-EXISTENCE assertion, and it is legitimate
  ONLY when the child's deliverable is itself a test, a check or a gate; on
  any other child, restate it as the behaviour those tests were meant to
  establish.
- **One proof mode per assertion, chosen in order.** The modes are
  `factory_captured`, then `host_captured`, then `human_attested`, and an
  assertion carries the FIRST of them that can actually prove it against
  the sandbox capabilities the display reports below. `factory_captured`
  is the default and needs no declaration. The other two are declared by
  POSITION — put the assertion under a `### Host-captured` or
  `### Human-attested` sub-heading inside the section, each carrying a
  non-empty `Reason:` line before its first bullet: the host surface or
  released-build requirement for the first, and why no agent session can
  exercise the proof for the second.
- **Reference the scenario that governs the assertion.** The section
  carries exactly one `References:` line naming the verbatim text of an
  existing H2 heading of the governed spec tree. Where a
  `## Scenario NN — ...` heading of `scenarios.md` states the behaviour an
  assertion names, THAT heading is the one to name, because the proof steps
  exercise the scenario's own Given/When/Then.
- **Never state the carrier relation inside the section.** Which plan
  assertions this child carries is recorded ONLY in the epic's carrier-map
  scope event; repeat it as prose BEFORE the Definition of Done heading if
  it helps a reader, never as a bullet inside the section. This is the rule
  a plan front-end trips most easily, because the carrier relation is
  exactly what the routing decision is about.

After the child is filed, DISPLAY the filing through the one public display
primitive every filing front-end uses:

```python
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    filing_display,
)

filing_advice = filing_display(item=child, cwd=Path.cwd())
```

Show every line. It carries the child's effective-criteria parse, each
assertion with its proof mode, the resolved sandbox capabilities (the committed
`dispatcher.sandbox_capabilities` array, or `sandbox-capabilities: unpublished`
when the key is unset), and every Definition-of-Done finding the host-side wall
can detect, each labelled `(mechanical)` or `(advisory)`. A child routed without
the section reports `definition-of-done: missing`. The display never refuses the
routing, but the two kinds of finding differ: a MECHANICAL finding WITHHOLDS
`ready`, so the child waits at `pending-approval` until it is repaired, while an
ADVISORY one does not and is instead surfaced by `needs-attention` while the
child rests in `ready`. Either kind is recorded on the child as a ledger
comment.

#### Child disposition

Disposing a plan child is **session-performable**. It changes where work
is TRACKED, not what the specification REQUIRES, so it is not a
spec-change decision and MUST NOT be escalated as one. Treating it as a
maintainer call deadlocks the archive gate for every epic that
accumulated scope creep: the gate refuses while a child is undisposed,
and the session that could dispose it declines to.

Call `close_plan_child(...)` for a child whose work is finished,
abandoned, or absorbed elsewhere, and `reparent_plan_child(...)` for one
that belongs under a different parent. Both take a `rationale` and write
it to the ledger — on the child and on the plan epic — BEFORE they mutate
anything, so a failed mutation leaves an explained intent rather than a
silent disposition. Re-parenting moves only the edge to this plan's epic;
every other edge the child carries is left alone.

Both refuse a **spec-change-tier** child — one carrying a spec commitment
— by raising `PlanDispositionRefusedError`. That child is human-gated by
routing: hand it to `propose-change` instead of disposing it here.

#### Record rate

A blocked session writes records instead of making progress: one wrote 15
handoff entries and about 12 research notes in a single day while it was
stuck, and nothing noticed, because every individual write was
legitimate.

Before appending a handoff entry or a research note, call
`plan_record_rate_warnings(entries=..., research_paths=...)` with the
timeline from `read_timeline(...)` and this thread's research-note paths.
It returns one warning per day that ran past the threshold — separately
for handoff entries, counted per author-day, and for research notes,
counted per day from the working tree's modification times.

Surface every warning it returns, then carry on. This guard only WARNS:
it never refuses a write, and exceeding the threshold is not an error. A
genuinely busy day is allowed to exceed it. What is NOT allowed is a
thread quietly accumulating a day's worth of records nobody sees, so the
warning MUST be surfaced rather than swallowed. When one fires, the
useful question is whether the thread is blocked on something that a
handoff entry cannot fix.

#### The plan Definition of Done

A plan is done when the outcome the maintainer asked for was OBSERVED —
not when its children closed. So the plan epic carries its own Definition
of Done, and it is authored at creation, never bolted on later.

Ask the maintainer what done means and record their answer in two places,
both written by `create_thread` from the one `PlanDefinitionOfDone` value:

- `statement` — the maintainer's own words, VERBATIM. Never reworded,
  summarized, or tidied. It lands in the initial research note, beside
  the assertions derived from it, so a later reader can audit the
  derivation against its source.
- `assertions` — one behavioural assertion per entry, each naming an
  observable behaviour or state of the delivered artifact on a surface a
  user or operator reaches. They become the `## Definition of Done`
  section at the head of the epic description.

An attended creation CONFIRMS the derived assertions with the maintainer
before creating the plan. An unattended creation MUST NOT invent them:
record them as session-derived in the first handoff entry.

Each plan assertion's proof mode is `host_captured` by default, with no
`Reason:` line required — a plan has one leg, and every plan assertion
that is not `human_attested` is exercised on a host. There is no
`factory_captured` mode for a plan assertion, because no factory run
executes against an epic. A `### Human-attested` sub-heading declares the
assertions beneath it `human_attested` and DOES owe a `Reason:` line,
exactly as on a work item. A reference line is optional: a plan may
precede the specification it will ratify.

#### The carrier map

Each plan assertion is carried by something: one or more child work-items,
or the plan's own Proof of Done record. That relation is recorded in ONE
place — a scope event's `carriers:` block — and nowhere else.

A scope event becomes a CARRIER-MAP event when you pass `carriers` to
`record_scope_event(...)`: one entry per plan assertion, in Definition of
Done order, of the form

- `<ordinal>: <work-item-id>[, <work-item-id>...]` — those children carry it
- `<ordinal>: plan-level proof` — the plan's own proof record discharges it

The scoping event, and every later scope event that adds, removes or
re-words a plan assertion or changes a carrier, MUST carry the block.
`record_scope_event` REFUSES a carrier-map event that leaves any plan
assertion unmapped, naming each one, and refuses one on an epic with no
gradeable Definition of Done section.

Omit `carriers` for a maintainer ruling or a deferral. Those do not
restate the map, are recorded exactly as before, and void nothing.

A closed carrier child does NOT by itself discharge the plan assertion it
carries. The map says who carries an assertion; the plan-level proof is
what discharges one.

#### The typed next action

The next action is epic metadata, not prose. Every open epic with a live
`plan/<slug>/` directory carries a `next_action` object with exactly
three keys, beside a `last_session` string naming who wrote it and when:

- `kind: impl` — factory implementation of one work-item. `ref` is that
  work-item's id, and the action executes as `impl:<ref>`.
- `kind: spec-op` — a spec-lifecycle operation. `ref` is
  `<operation>:<topic>`, which is itself the action id.
- `kind: human` — a person is needed. `ref` may be empty or may name the
  attention item or question that carries the ask.
- `kind: none` — nothing is recorded, and `ref` is empty.

`text` is one imperative sentence a person can read with no other
context. Write all four fields only through `append_handoff(...)`,
`append_supervisor_handoff(...)`, or `set_next_action(...)`; never
hand-edit epic metadata.

A prose `next action:` line may still appear in a handoff body for a
human reader, but it carries no authority. When the two disagree the
metadata wins — a wrapped prose line truncated the instruction twice on
a live tenant, deleting a constraint in one case and the factory route
in the other, while the resume reported one confident action.

#### Unattended resume

A resume is *unattended* when the environment variable
`LIVESPEC_PLAN_UNATTENDED` is set to a truthy value (`1`, `true`, `yes`,
or `on`, case- and whitespace-insensitive). The overseer daemon sets it
on the resume it triggers after a context-threshold restart, where no
operator is present to answer a question. Nothing else sets it: an
operator-launched session leaves it unset and keeps the picker.

Call `resume_directive(config=..., epic_id=..., unattended=...)`. It
reads the epic's `next_action` — it parses no comment body — and returns
`ask`, `next_action`, a `reason`, and `findings`:

- `ask` is false only when the session is unattended AND the `kind` is
  `impl` or `spec-op` AND the `ref` is non-empty. Take the returned
  `next_action` action id directly and do not raise the which-action
  picker.
- `ask` is true in every other case — an attended session, an epic
  carrying no typed pointer, a `human` or `none` kind, or a dispatchable
  kind with an empty ref. Present the picker and wait.

An attended resume presents the epic's `next_action` as the default
choice of that picker.

Report the `reason` when the picker is raised in an unattended session:
that string is how a hands-off restart explains why it stopped rather
than parking silently on a question nobody will see.

ALWAYS surface every entry in `findings`, in both modes. Today it carries
one: `plan-definition-of-done: missing`, for a plan epic created before
that section was required. An ATTENDED resume of such an epic MUST author
the section with the maintainer before recording any further carrier-map
event. An UNATTENDED resume MUST NOT author the assertions on the
maintainer's behalf — `resume_directive` has already set `next_action` to
`kind: human` naming the gap, and `ask` is true — unless `next_action` was
already `kind: impl`, which it still takes, because that names work
already filed and admitted. The finding is reported either way: reported
and acted on are different things.

### Step 4 - Handoff Timeline Requirements

A handoff entry is ready only when a fresh session can continue from the
ledger timeline without chat history:

1. The call wrote exactly one typed `next_action` onto the epic.
2. Every path it cites exists and is committed.
3. If the next action is implementation work, it names the factory route:
   `kind: impl` with the work-item id as its `ref`, which the `drive`
   operation executes as `impl:<ref>`, or a Dispatcher drain. Only items
   explicitly recorded as factory-ineligible may name an in-session
   implementation route.
4. It does not embed a parallel checklist or status queue. Status is
   composed from the ledger via `list-work-items` and `next`.

### Step 5 - Archive Gates

A plan remains live until its work is genuinely complete:
implemented, merged, and, where a release applies, shipped and verified.
Do not archive merely because the plan epic's ledger status moved to
closed; closed can also mean regroomed out, superseded, or otherwise
retired without completing the work.

The only exception is an explicit handoff at archive time: any remaining
work must be transferred to named follow-up plan(s) or work-item(s), and
the archive record must state those names exactly. Mechanical enforcement
of this corrected archive rule is tracked outside this repo in
`livespec-dev-tooling-5asgvm` and the related converse-gap item
`livespec-dev-tooling-q3emww`.

Archiving has three required legs:

1. Mechanical child disposition. Refuse archive if any child of the plan
   epic is not disposed. Undisposed means any child work-item whose
   ledger status is not closed.
2. Completeness-review evidence. If the ledger timeline lacks valid
   independent completeness-review evidence after the mechanical leg
   passes, commission one fresh independent adversarial reviewer. The
   reviewer must have had no role in the plan's implementation, compare
   every research requirement and explicit deferral against the complete
   child set, spot-check closure evidence against the forge, and record
   the result durably through `record_completeness_review_evidence(...)`,
   called from the REVIEWER's own session. Keep the plan live until that
   durable evidence exists. A self-review, an unrecorded result, or a
   review that does not attest complete requirement-carrier coverage is
   not evidence.

   The self-review half of that is MECHANICAL, and the archive names it
   on its own: `archive_thread(...)` compares the evidence record's
   computed `reviewer-identity` against its own computed archiving
   identity and refuses, naming both the identity and the evidence id,
   when they are equal. Two other refusals sit beside it and are
   deliberately distinct, because each prescribes a different next
   action: evidence that is absent or does not fully attest reports that
   evidence is required, and an invocation whose own identity cannot be
   computed at all reports which party went unnamed rather than archiving
   on a comparison it could not make.

   The RECENCY half is mechanical too, and it is the second thing the
   archive names on its own. Every evidence record states the child
   work-item ids it reviewed, and `archive_thread(...)` refuses while that
   set differs from the epic's child set at archive time — naming each
   child added and each child removed since the review — or while the
   record predates the latest status change any current child reports,
   naming that child and the instant it changed at. A wholly stale
   timeline is handled exactly as a missing one: a fresh reviewer is
   commissioned, and the refusal carries the stale account rather than
   reporting that evidence is required, so nobody is sent hunting for a
   record already on the timeline. Until this landed, a record of ANY age
   satisfied the leg forever: evidence written for one plan epic on
   2026-08-17 still validated five days later, after seven further
   children had landed across four repositories that its reviewer never
   saw.

   What the gate does NOT verify is worth knowing before citing a passing
   one. `separate-reviewer` and `attests-complete-requirement-coverage`
   are SELF-DECLARED by whoever wrote the comment and are cross-checked
   against nothing; the gate establishes that they were claimed, that the
   party claiming them is not the party archiving, and that the scope they
   were claimed about is this plan's as it now stands. The reviewer's
   actual independence of the plan's IMPLEMENTATION — as opposed to its
   independence of the archiving session — is still routed socially, by
   whoever commissions the review. The reviewed child set is likewise
   written by the reviewer, so it says what the reviewer CLAIMS to have
   read; what the gate adds is that the claim is checked against the
   ledger, which the two booleans are not.
3. The plan's own Proof of Done. The epic must carry a Definition of Done
   section, and the latest plan Proof of Done record on it whose verdict
   is `verified` or `not_reproduced` must be `verified`, must cover every
   plan assertion that is not `human_attested`, and must postdate both the
   latest `captured` record and the last carrier-map event. Each
   `human_attested` plan assertion is covered separately, by a
   `human_attested` record postdating that same event. A later
   `human_attested` record does not unseat an earlier `verified` one, and a
   ruling or deferral that is not a carrier-map event voids neither.
   `archive_thread(...)` refuses while this leg is unmet, naming each
   unproved plan assertion, and leaves the plan directory and the epic
   unchanged. The independent completeness reviewer of leg 2 may be the
   verifying party of the plan record.

Publish every plan record through the one posting primitive, never by
hand:

```text
dispatcher.py post-plan-record --repo <path> --epic <id> \
    --verdict <captured|verified|not_reproduced|human_attested> \
    --record <payload.json>
```

The payload carries only what the publishing session holds: the build
identity it exercised, and per plan assertion the numbered steps, the
proof they produced, and whether they reproduced. The primitive computes
the rest — the header, the UTC timestamp, the publishing identity, and
each assertion's proof mode read off the plan's own Definition of Done —
and refuses a `verified` post whose computed identity equals the identity
that captured the steps it replays. A DIFFERENT session must replay them.

Where a release applies to the plan's work — the governed repository
carries at least one release tag — the steps must run against the released
artifact installed through its normal installation path. The archive gate
rejects a record that states `release: none`, or names a release tag the
repository does not carry, and names the missing release identity in its
refusal.

After the fact, the `plan_close_proof` conformance verdict reports a plan
epic closed later than the proof leg's ratification date whose timeline
carries no `verified` plan record; an epic closed on or before that date is
out of its scope.

Before the move, sweep the working tree for code that reads the plan
directory by path. Both ledger gates are blind to it: they enumerate
children and read evidence, and neither looks at the tree the rename
mutates. A plan that shipped wrappers, fixtures, or a rehearsal package
is exactly the shape that breaks — archiving `beads-v1-1-2-upgrade` moved
a rehearsal package two live test modules held as hardcoded path
constants, and the archive pull request came back with 33
`FileNotFoundError`s after the epic was already closed and stamped.

`archive_thread(...)` runs the sweep itself and REFUSES the move while
any file outside `plan/` references `plan/<topic>/`, naming every one; a
session can also run `outside_plan_path_references(...)` first to see the
hit list. The sweep skips the `plan/` tree, `.git`, `.venv`,
`node_modules`, and vendored trees, and it catches both the posix literal
`plan/<topic>/…` and the segment-join form `ROOT / "plan" / "<topic>" /
…`. Repoint each hit — insert `archive` into its path — or retire it, and
land those edits in the SAME pull request as the move. A hit left for a
follow-up is a red pull request on an archive whose ledger has already
been mutated.

After every gate passes, close the epic and move the whole directory:

```text
git mv plan/<topic>/ plan/archive/<topic>/
```

Leave nothing at `plan/<topic>/`: no stub, marker, forwarding note, or
empty directory. If unresolved work remains, either keep the plan live
with its epic open, or transfer every blocker to another live plan
or work-item before archiving.

## Important Properties

- Research is filesystem-held; handoffs are ledger-held; the next action
  is typed epic metadata that no line wrap can truncate.
- An unattended resume with a dispatchable typed next action takes it;
  the which-action picker is the attended-mode behavior.
- Child disposition is session-performable with a recorded rationale;
  only a spec-change-tier child refuses.
- Runaway record authoring is visible: a day past the record-rate
  threshold warns, and never refuses a write.
- Creation writes one research note plus one epic anchor and nothing
  else.
- Status is derived from the ledger and never shadowed in files.
- Scope events cut requirements and explicit deferrals before
  implementation children are admitted.
- Archive has three gates: no undisposed children, independent
  completeness-review evidence, and a verified plan Proof of Done record
  taken against the released build; the operation commissions the missing
  reviewer only after all children are disposed, and still refuses to
  archive before valid durable evidence and a verified plan record exist.
- A plan assertion is not transferable. Remaining WORK may be handed to
  named follow-ups at archive time; an unproved plan assertion leaves only
  the keep-the-plan-live disposition.
- The operation never authors `handoff.md`.

## What This Operation Does Not Do

- Does not write status or queues into planning files.
- Does not create a thread from strict `<slug>` resume mode.
- Does not implement child work inline.
- Does not escalate a plan child's closure or re-parenting to a human,
  except for a spec-change-tier child.
- Does not accept a self-review, an unrecorded result, or a partial
  coverage attestation as archive evidence.
